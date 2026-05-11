"""Integration coverage for the task trace debugging surface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from prometheus_client import generate_latest

import AutoGLM_GUI.api.history as history_api
import AutoGLM_GUI.layered_agent_service as layered_service
from AutoGLM_GUI.actions import ActionHandler
from AutoGLM_GUI.devices.adb_device import ADBDevice
from AutoGLM_GUI.metrics import get_metrics_registry, reset_trace_latency_metrics
from AutoGLM_GUI.task_manager import TaskManager
from AutoGLM_GUI.task_store import TaskStatus, TaskStore
from AutoGLM_GUI.trace import trace_span


pytestmark = [pytest.mark.integration]


def _load_trace_records(trace_file: Path, trace_id: str) -> list[dict[str, Any]]:
    assert trace_file.exists(), f"Trace file was not written: {trace_file}"
    records: list[dict[str, Any]] = []
    for line in trace_file.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("trace_id") == trace_id:
            records.append(record)
    return records


def _fake_adb_run(*_: Any, **__: Any) -> SimpleNamespace:
    return SimpleNamespace(stdout="", stderr="", returncode=0)


class _FakePlannerStreamingResult:
    final_output = "Planner confirmed the debug scenario completed."

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.cancelled = False

    def cancel(self, mode: str = "immediate") -> None:
        self.cancelled = True

    async def stream_events(self):
        session = layered_service.TracedSQLiteSession(f"trace-test-{self.device_id}")
        await session.add_items(
            [
                {
                    "role": "user",
                    "content": "打开微信，搜索张三，发送你好",
                }
            ]
        )
        await session.get_items()

        yield RawResponsesStreamEvent(
            data=SimpleNamespace(type="response.created"),
        )
        yield RunItemStreamEvent(
            name="tool_called",
            item=SimpleNamespace(
                type="tool_call_item",
                raw_item={
                    "name": "chat",
                    "arguments": json.dumps(
                        {
                            "device_id": self.device_id,
                            "message": "打开微信，搜索张三，发送你好",
                        },
                        ensure_ascii=False,
                    ),
                },
            ),
        )

        with trace_span(
            "layered.tool.chat.run_agent",
            attrs={"device_id": self.device_id, "agent_type": "TraceFakeAgent"},
        ):
            with trace_span(
                "agent.step",
                attrs={"step": 1, "agent_type": "TraceFakeAgent"},
            ):
                with trace_span(
                    "step.capture_screenshot",
                    attrs={"step": 1, "agent_type": "TraceFakeAgent"},
                ):
                    pass
                with trace_span(
                    "step.llm",
                    attrs={
                        "step": 1,
                        "agent_type": "TraceFakeAgent",
                        "model_name": "mock-glm-model",
                        "message_count": 1,
                    },
                ):
                    await asyncio.sleep(0.01)
                with trace_span(
                    "step.parse_action",
                    attrs={"step": 1, "agent_type": "TraceFakeAgent"},
                ):
                    pass
                with trace_span(
                    "step.execute_action",
                    attrs={
                        "step": 1,
                        "agent_type": "TraceFakeAgent",
                        "action_name": "Tap",
                    },
                ):
                    result = ActionHandler(ADBDevice(self.device_id)).execute(
                        {"_metadata": "do", "action": "Tap", "element": [500, 500]},
                        screen_width=1000,
                        screen_height=1000,
                    )
                    assert result.success is True
                with trace_span(
                    "step.update_context",
                    attrs={"step": 1, "agent_type": "TraceFakeAgent"},
                ):
                    with trace_span(
                        "memory.write",
                        attrs={"step": 1, "memory_type": "fake_agent_context"},
                    ):
                        pass

        yield RunItemStreamEvent(
            name="tool_output",
            item=SimpleNamespace(
                type="tool_call_output_item",
                output=json.dumps(
                    {"result": "已发送你好给张三", "steps": 1, "success": True},
                    ensure_ascii=False,
                ),
            ),
        )
        yield RawResponsesStreamEvent(
            data=SimpleNamespace(type="response.completed"),
        )
        yield RunItemStreamEvent(
            name="message_output_created",
            item=SimpleNamespace(
                type="message_output_item",
                raw_item=SimpleNamespace(
                    content=[
                        SimpleNamespace(
                            text="我已经确认消息发送完成。",
                        )
                    ]
                ),
            ),
        )
        await session.clear_session()


def test_layered_task_trace_observability_covers_debug_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))

    import AutoGLM_GUI.adb.device as adb_device_module

    monkeypatch.setattr(adb_device_module.subprocess, "run", _fake_adb_run)
    monkeypatch.setattr(
        adb_device_module.TIMING_CONFIG.device,
        "default_tap_delay",
        0.0,
    )

    reset_trace_latency_metrics()

    store = TaskStore(tmp_path / "tasks.db")
    manager = TaskManager(store)

    def fake_start_run(
        *,
        task_id: str,
        session_id: str,
        message: str,
    ) -> layered_service.LayeredTaskRun:
        assert message == "打开微信，搜索张三，发送你好"
        with trace_span(
            "layered.planner.run_streamed",
            attrs={
                "task_id": task_id,
                "session_id": session_id,
                "max_turns": 100000,
            },
        ):
            return layered_service.LayeredTaskRun(
                task_id=task_id,
                session_id=session_id,
                result=_FakePlannerStreamingResult("adb-debug-device"),
            )

    monkeypatch.setattr(layered_service, "start_run", fake_start_run)
    monkeypatch.setattr(history_api, "task_store", store)

    async def scenario() -> dict[str, Any]:
        await manager.start()
        try:
            session = await manager.create_chat_session(
                device_id="adb-debug-device",
                device_serial="serial-debug",
                mode="layered",
            )
            task = await manager.submit_chat_task(
                session_id=str(session["id"]),
                device_id="adb-debug-device",
                device_serial="serial-debug",
                message="打开微信，搜索张三，发送你好",
            )
            final_task = await manager.wait_for_task(str(task["id"]), timeout=5)
            assert final_task is not None
            return final_task
        finally:
            await manager.shutdown()

    try:
        final_task = asyncio.run(scenario())

        assert final_task["status"] == TaskStatus.SUCCEEDED.value
        assert final_task["trace_id"]
        assert final_task["step_count"] == 1

        events = store.list_task_events(str(final_task["id"]))
        event_types = [event["event_type"] for event in events]
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "message" in event_types
        assert "trace_summary" in event_types

        trace_summary_event = next(
            event for event in events if event["event_type"] == "trace_summary"
        )
        trace_summary = trace_summary_event["payload"]["summary"]
        assert trace_summary["trace_id"] == final_task["trace_id"]
        assert trace_summary["steps"] == 1

        history_record = history_api._build_history_record_from_task(final_task)
        assert history_record.trace_id == final_task["trace_id"]
        assert history_record.trace_summary is not None
        assert history_record.step_timings

        trace_records = _load_trace_records(trace_file, str(final_task["trace_id"]))
        span_names = {record["name"] for record in trace_records}
        expected_spans = {
            "layered.planner.run_streamed",
            "layered.planner.stream",
            "model.call",
            "tool.call",
            "tool.result",
            "layered.tool.chat.run_agent",
            "memory.read",
            "memory.write",
            "memory.clear",
            "agent.step",
            "step.capture_screenshot",
            "step.llm",
            "step.parse_action",
            "step.execute_action",
            "step.update_context",
            "action.execute",
            "device.tap",
            "adb.tap",
            "task_store.event.append",
            "task_store.task.finish",
        }
        assert expected_spans <= span_names

        metrics_output = generate_latest(get_metrics_registry()).decode("utf-8")
        assert "autoglm_trace_task_duration_seconds_bucket" in metrics_output
        assert 'autoglm_trace_task_duration_seconds_count{source="layered"} 1.0' in (
            metrics_output
        )
        assert "autoglm_trace_step_duration_seconds_bucket" in metrics_output
        assert "autoglm_trace_component_duration_seconds_bucket" in metrics_output
    finally:
        reset_trace_latency_metrics()
        store.close()
