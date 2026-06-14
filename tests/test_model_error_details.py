"""Tests for structured model error diagnostics."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from openai import BadRequestError

from AutoGLM_GUI.agents.gemini.async_agent import AsyncGeminiAgent
import AutoGLM_GUI.layered_agent_service as layered_agent_service
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import Screenshot
from AutoGLM_GUI.model.error_details import (
    serialize_model_error,
    serialize_model_error_async,
)


class _FakeDevice:
    device_id = "fake-001"

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        return Screenshot(base64_data="screen", width=1080, height=2400)

    def get_current_app(self) -> str:
        return "com.example.app"


class _FailingGeminiAgent(AsyncGeminiAgent):
    async def _call_llm_with_tools(
        self,
    ) -> tuple[str, str | None, str, dict[str, Any]]:
        request = httpx.Request("POST", "https://example.test/v1/chat/completions")
        response = httpx.Response(
            400,
            request=request,
            headers={
                "authorization": "Bearer secret",
                "x-request-id": "req-123",
                "content-type": "application/json",
            },
            json={"error": {"message": "bad request", "code": "invalid_request"}},
        )
        raise BadRequestError(
            "bad request",
            response=response,
            body=response.json(),
        )


class _FailingPlannerResult:
    final_output = ""

    async def stream_events(self):
        if False:
            yield None
        raise RuntimeError("planner boom")

    def cancel(self, mode: str = "immediate") -> None:
        pass


class _AsyncBodyStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes):
        self.body = body

    async def __aiter__(self):
        yield self.body


def test_serialize_model_error_redacts_sensitive_headers() -> None:
    request = httpx.Request(
        "POST", "https://user:pass@example.test/v1/chat/completions?token=secret"
    )
    response = httpx.Response(
        401,
        request=request,
        headers={
            "authorization": "Bearer secret",
            "x-api-key": "secret-key",
            "x-request-id": "req-unauthorized",
        },
        text="Unauthorized",
    )
    exc = BadRequestError("Unauthorized", response=response, body=response.text)

    details = serialize_model_error(
        exc,
        model_config=ModelConfig(
            base_url="https://user:pass@example.test/v1?token=secret#fragment",
            api_key="secret",
            model_name="demo-model",
        ),
        call_site="tests.call_site",
    )

    assert details["kind"] == "model_http_error"
    assert details["status_code"] == 401
    assert details["request_id"] == "req-unauthorized"
    assert details["response_body"] == "Unauthorized"
    assert details["response_headers"]["authorization"] == "[REDACTED]"
    assert details["response_headers"]["x-api-key"] == "[REDACTED]"
    assert details["model_name"] == "demo-model"
    assert details["base_url"] == "https://example.test/v1"
    assert details["call_site"] == "tests.call_site"


def test_serialize_model_error_reads_unread_streaming_response_body() -> None:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        stream=httpx.ByteStream(b"streamed model failure"),
    )
    exc = BadRequestError("bad request", response=response, body=None)

    details = serialize_model_error(
        exc,
        model_config=ModelConfig(
            base_url="https://example.test/v1",
            api_key="secret",
            model_name="demo-model",
        ),
        call_site="tests.call_site",
    )

    assert details["kind"] == "model_http_error"
    assert details["response_body"] == "streamed model failure"


def test_serialize_model_error_async_reads_async_streaming_body() -> None:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        stream=_AsyncBodyStream(b"async streamed model failure"),
    )
    exc = BadRequestError("bad request", response=response, body=None)

    async def run() -> dict[str, Any]:
        return await serialize_model_error_async(
            exc,
            model_config=ModelConfig(
                base_url="https://example.test/v1",
                api_key="secret",
                model_name="demo-model",
            ),
            call_site="tests.call_site",
        )

    details = asyncio.run(run())

    assert details["kind"] == "model_http_error"
    assert details["response_body"] == "async streamed model failure"


def test_gemini_model_error_events_include_structured_details(
    tmp_path,
    monkeypatch,
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))

    agent = _FailingGeminiAgent(
        model_config=ModelConfig(
            base_url="https://user:pass@example.test/v1?token=secret",
            api_key="secret",
            model_name="demo-model",
        ),
        agent_config=AgentConfig(max_steps=1, verbose=True),
        device=_FakeDevice(),
    )

    async def run() -> list[dict[str, Any]]:
        agent._prepare_initial_context("task", "screen", "com.example.app")
        return [event async for event in agent._execute_step()]

    events = asyncio.run(run())
    error_event = next(event for event in events if event["type"] == "error")
    step_event = next(event for event in events if event["type"] == "step")

    error_details = error_event["data"]["error_details"]
    assert error_event["data"]["message"] == "Model error: bad request"
    assert step_event["data"]["error_details"] == error_details
    assert error_details["kind"] == "model_http_error"
    assert error_details["status_code"] == 400
    assert error_details["request_id"] == "req-123"
    assert error_details["response_headers"]["authorization"] == "[REDACTED]"
    assert error_details["base_url"] == "https://example.test/v1"
    assert "traceback" not in error_details
    assert "bad request" in error_details["response_body"]

    trace_records = [
        json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines()
    ]
    llm_span = next(record for record in trace_records if record["name"] == "step.llm")
    assert llm_span["status"] == "error"
    assert llm_span["attrs"]["http.status_code"] == 400
    assert llm_span["attrs"]["http.response_headers"]["authorization"] == "[REDACTED]"


def test_layered_planner_error_event_does_not_expose_traceback(monkeypatch) -> None:
    monkeypatch.setattr(
        layered_agent_service,
        "_planner_model_config",
        lambda: ModelConfig(
            base_url="https://example.test/v1",
            api_key="secret",
            model_name="planner-model",
        ),
    )
    run = layered_agent_service.LayeredTaskRun(
        task_id="task-1",
        session_id="session-1",
        result=_FailingPlannerResult(),
    )

    async def collect_events() -> list[dict[str, Any]]:
        return [event async for event in run.stream_events()]

    events = asyncio.run(collect_events())
    error_event = next(event for event in events if event["type"] == "error")
    details = error_event["payload"]["error_details"]

    assert details["exception_type"] == "RuntimeError"
    assert details["message"] == "planner boom"
    assert details["model_name"] == "planner-model"
    assert "traceback" not in details
