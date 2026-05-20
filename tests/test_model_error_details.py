"""Tests for structured model error diagnostics."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from openai import BadRequestError

from AutoGLM_GUI.agents.gemini.async_agent import AsyncGeminiAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import Screenshot
from AutoGLM_GUI.model.error_details import serialize_model_error


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


def test_serialize_model_error_redacts_sensitive_headers() -> None:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
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
            base_url="https://example.test/v1",
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


def test_gemini_model_error_events_include_structured_details(
    tmp_path,
    monkeypatch,
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))

    agent = _FailingGeminiAgent(
        model_config=ModelConfig(
            base_url="https://example.test/v1",
            api_key="secret",
            model_name="demo-model",
        ),
        agent_config=AgentConfig(max_steps=1, verbose=False),
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
    assert "bad request" in error_details["response_body"]

    trace_records = [
        json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines()
    ]
    llm_span = next(record for record in trace_records if record["name"] == "step.llm")
    assert llm_span["status"] == "error"
    assert llm_span["attrs"]["http.status_code"] == 400
    assert llm_span["attrs"]["http.response_headers"]["authorization"] == "[REDACTED]"
