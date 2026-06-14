"""Tests for lightweight trace spans."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from AutoGLM_GUI.trace_export import export_otlp_jsonl
from AutoGLM_GUI.trace import (
    clear_trace_data,
    current_trace_id,
    delete_replay_run,
    get_step_timing_summary,
    get_trace_timing_summary,
    list_step_timing_summaries,
    trace_context,
    trace_sleep,
    trace_span,
    write_trace_artifact,
    write_replay_event,
    write_replay_task_start,
)


def _read_trace_records(trace_file: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in trace_file.read_text().splitlines()]


def _read_replay_records(trace_file: Path, trace_id: str) -> list[dict[str, object]]:
    replay_file = trace_file.parent / "runs" / trace_id / "replay.jsonl"
    return [json.loads(line) for line in replay_file.read_text().splitlines()]


def test_trace_span_writes_nested_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with trace_span("parent", new_trace=True) as parent_span:
        with trace_span("child", attrs={"value": 1, "path": Path("/tmp/demo")}):
            trace_sleep(0, name="sleep.test")

    records = _read_trace_records(trace_file)

    assert len(records) == 3

    child_record = next(record for record in records if record["name"] == "child")
    parent_record = next(record for record in records if record["name"] == "parent")
    sleep_record = next(record for record in records if record["name"] == "sleep.test")

    assert child_record["trace_id"] == parent_record["trace_id"]
    assert child_record["schema"] == "autoglm.trace.span.v1"
    assert child_record["record_type"] == "span"
    assert child_record["parent_span_id"] == parent_span.span_id
    assert sleep_record["parent_span_id"] == child_record["span_id"]
    assert child_record["attrs"] == {"path": "/tmp/demo", "value": 1}


def test_trace_context_sets_trace_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with trace_context("trace-123"):
        assert current_trace_id() == "trace-123"
        with trace_span("inside-context"):
            pass

    records = _read_trace_records(trace_file)
    assert records[0]["trace_id"] == "trace-123"


def test_trace_span_records_error_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with pytest.raises(RuntimeError, match="boom"):
        with trace_span("error-span", new_trace=True):
            raise RuntimeError("boom")

    records = _read_trace_records(trace_file)
    assert records[0]["name"] == "error-span"
    assert records[0]["status"] == "error"
    assert records[0]["error"] == {"message": "boom", "type": "RuntimeError"}


def test_trace_collects_step_timing_summaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with trace_context("trace-step"):
        with trace_span("agent.step", attrs={"step": 1}):
            with trace_span("step.capture_screenshot", attrs={"step": 1}):
                pass
            with trace_span("step.llm", attrs={"step": 1}):
                trace_sleep(0.001, name="sleep.test")
            with trace_span("step.execute_action", attrs={"step": 1}):
                with trace_span("adb.tap"):
                    pass

            step_summary = get_step_timing_summary(1)
            assert step_summary is not None
            assert step_summary["trace_id"] == "trace-step"
            assert step_summary["step"] == 1
            assert step_summary["total_duration_ms"] >= step_summary["llm_duration_ms"]
            assert step_summary["sleep_duration_ms"] > 0
            assert step_summary["adb_duration_ms"] >= 0

    summaries = list_step_timing_summaries(trace_id="trace-step")
    assert len(summaries) == 1
    assert summaries[0]["screenshot_duration_ms"] >= 0

    trace_summary = get_trace_timing_summary(
        trace_id="trace-step",
        total_duration_ms=42.0,
        steps=1,
    )
    assert trace_summary == {
        "trace_id": "trace-step",
        "steps": 1,
        "total_duration_ms": 42.0,
        "screenshot_duration_ms": summaries[0]["screenshot_duration_ms"],
        "current_app_duration_ms": 0.0,
        "llm_duration_ms": summaries[0]["llm_duration_ms"],
        "parse_action_duration_ms": 0.0,
        "execute_action_duration_ms": summaries[0]["execute_action_duration_ms"],
        "update_context_duration_ms": 0.0,
        "adb_duration_ms": summaries[0]["adb_duration_ms"],
        "sleep_duration_ms": summaries[0]["sleep_duration_ms"],
        "other_duration_ms": 0.0,
    }

    clear_trace_data("trace-step")
    assert get_step_timing_summary(1, trace_id="trace-step") is None


def test_replay_trace_writes_step_with_screenshot_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")
    monkeypatch.setenv("AUTOGLM_TRACE_REPLAY_ENABLED", "1")

    screenshot = base64.b64encode(b"fake png bytes").decode("ascii")
    task = {
        "id": "task-1",
        "source": "chat",
        "executor_key": "classic_chat",
        "device_id": "device-1",
        "device_serial": "serial-1",
        "input_text": "打开设置",
        "status": "RUNNING",
    }
    write_replay_task_start(
        task_id="task-1",
        trace_id="trace-replay",
        task=task,
        source="classic_chat",
    )
    write_replay_event(
        task_id="task-1",
        trace_id="trace-replay",
        source="classic_chat",
        task=task,
        event_record={
            "task_id": "task-1",
            "seq": 1,
            "event_type": "step",
            "role": "assistant",
            "created_at": "2026-05-13T12:00:00",
            "payload": {
                "step": 1,
                "thinking": "点击设置按钮",
                "action": {"_metadata": "do", "action": "Tap", "element": [1, 2]},
                "success": True,
                "finished": False,
                "message": None,
                "screenshot": screenshot,
                "timings": {"step": 1, "llm_duration_ms": 12.0},
            },
        },
    )

    records = _read_replay_records(trace_file, "trace-replay")
    assert [record["event_seq"] for record in records] == [0, 1]
    assert records[0]["event_name"] == "autoglm.task.start"
    step = records[1]["step"]
    assert step["thinking"] == "点击设置按钮"
    assert step["action"]["action"] == "Tap"
    assert step["timings"]["llm_duration_ms"] == 12.0
    assert screenshot not in json.dumps(step, ensure_ascii=False)

    screenshot_ref = step["artifacts"]["screenshot"]
    assert screenshot_ref["path"] == "artifacts/step_0001_screen.png"
    artifact_path = trace_file.parent / "runs" / "trace-replay" / screenshot_ref["path"]
    assert artifact_path.read_bytes() == b"fake png bytes"


def test_replay_screenshot_capture_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    screenshot = base64.b64encode(b"screen").decode("ascii")

    monkeypatch.setenv("AUTOGLM_TRACE_CAPTURE_SCREENSHOT", "off")
    write_replay_event(
        task_id="task-1",
        trace_id="trace-off",
        source="classic_chat",
        event_record={
            "seq": 1,
            "event_type": "step",
            "role": "assistant",
            "created_at": "now",
            "payload": {"step": 1, "success": False, "screenshot": screenshot},
        },
    )
    off_step = _read_replay_records(trace_file, "trace-off")[0]["step"]
    assert off_step["artifacts"] == {}

    monkeypatch.setenv("AUTOGLM_TRACE_CAPTURE_SCREENSHOT", "on_error")
    write_replay_event(
        task_id="task-1",
        trace_id="trace-on-error",
        source="classic_chat",
        event_record={
            "seq": 1,
            "event_type": "step",
            "role": "assistant",
            "created_at": "now",
            "payload": {"step": 1, "success": True, "screenshot": screenshot},
        },
    )
    write_replay_event(
        task_id="task-1",
        trace_id="trace-on-error",
        source="classic_chat",
        event_record={
            "seq": 2,
            "event_type": "step",
            "role": "assistant",
            "created_at": "now",
            "payload": {"step": 2, "success": False, "screenshot": screenshot},
        },
    )
    records = _read_replay_records(trace_file, "trace-on-error")
    assert records[0]["step"]["artifacts"] == {}
    assert "screenshot" in records[1]["step"]["artifacts"]


def test_replay_trace_can_be_disabled_and_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")
    monkeypatch.setenv("AUTOGLM_TRACE_REPLAY_ENABLED", "0")

    write_replay_event(
        task_id="task-1",
        trace_id="trace-disabled",
        source="classic_chat",
        event_record={
            "seq": 1,
            "event_type": "thinking",
            "role": "assistant",
            "created_at": "now",
            "payload": {"chunk": "hello"},
        },
    )
    assert not (trace_file.parent / "runs" / "trace-disabled").exists()

    monkeypatch.setenv("AUTOGLM_TRACE_REPLAY_ENABLED", "1")
    write_replay_event(
        task_id="task-1",
        trace_id="trace-delete",
        source="classic_chat",
        event_record={
            "seq": 1,
            "event_type": "thinking",
            "role": "assistant",
            "created_at": "now",
            "payload": {"chunk": "hello"},
        },
    )
    assert (trace_file.parent / "runs" / "trace-delete").exists()
    assert delete_replay_run("trace-delete") is True
    assert not (trace_file.parent / "runs" / "trace-delete").exists()


def test_replay_trace_defensive_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")
    monkeypatch.setenv("AUTOGLM_TRACE_REPLAY_ENABLED", "1")

    assert delete_replay_run(None) is False
    assert delete_replay_run("missing-run") is False

    artifact = write_trace_artifact(
        trace_id="trace-defensive",
        name="   ...   ",
        mime_type="text/plain",
        data_bytes=b"artifact bytes",
    )
    assert artifact is not None
    assert artifact["id"] == "artifact"
    assert artifact["path"] == "artifacts/artifact.txt"

    decoded_artifact = write_trace_artifact(
        trace_id="trace-defensive",
        name="raw-response",
        mime_type="application/json",
        data_base64=base64.b64encode(b"{}").decode("ascii").rstrip("="),
    )
    assert decoded_artifact is not None
    assert decoded_artifact["path"] == "artifacts/raw-response.json"

    with pytest.raises(ValueError, match="data_base64 or data_bytes is required"):
        write_trace_artifact(
            trace_id="trace-defensive",
            name="missing-data",
            mime_type="application/json",
        )

    created_at = datetime(2026, 5, 13, 12, tzinfo=timezone.utc)
    write_replay_event(
        task_id="task-1",
        trace_id="trace-defensive",
        source="classic_chat",
        event_record={
            "seq": 1,
            "event_type": "message",
            "role": "assistant",
            "created_at": created_at,
            "payload": {
                "path": tmp_path / "payload.json",
                "timestamp": created_at,
                "custom": RuntimeError("boom"),
            },
        },
    )
    write_replay_event(
        task_id="task-1",
        trace_id="trace-defensive",
        source="classic_chat",
        event_record={
            "seq": 2,
            "event_type": "message",
            "role": "assistant",
            "created_at": "now",
            "payload": ["not", "a", "dict"],
        },
    )

    monkeypatch.setenv("AUTOGLM_TRACE_CAPTURE_SCREENSHOT", "invalid-mode")
    write_replay_event(
        task_id="task-1",
        trace_id="trace-defensive",
        source="classic_chat",
        event_record={
            "seq": 3,
            "event_type": "step",
            "role": "assistant",
            "created_at": "now",
            "payload": {
                "step": 3,
                "success": True,
                "screenshot": base64.b64encode(b"x").decode("ascii").rstrip("="),
            },
        },
    )

    records = _read_replay_records(trace_file, "trace-defensive")
    message_payload = records[0]["payload"]
    assert message_payload["path"] == str(tmp_path / "payload.json")
    assert message_payload["timestamp"] == created_at.isoformat()
    assert message_payload["custom"] == "boom"
    assert records[1]["payload"] == {}
    assert records[2]["step"]["artifacts"]["screenshot"]["size_bytes"] == 1

    monkeypatch.setenv("AUTOGLM_TRACE_REPLAY_ENABLED", "0")
    assert (
        write_trace_artifact(
            trace_id="trace-disabled-artifact",
            name="disabled",
            mime_type="text/plain",
            data_bytes=b"disabled",
        )
        is None
    )
    assert (
        write_replay_task_start(
            task_id="task-disabled",
            trace_id="trace-disabled-start",
            task={"id": "task-disabled"},
            source="classic_chat",
        )
        is None
    )


def test_export_trace_otlp_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_file = tmp_path / "trace.jsonl"
    output_file = tmp_path / "otlp.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with trace_context("trace-export"):
        with trace_span(
            "step.llm",
            attrs={"step": 1, "model_name": "mock-model"},
        ):
            pass
        with pytest.raises(RuntimeError, match="export boom"):
            with trace_span("action.execute", attrs={"step": 1}):
                raise RuntimeError("export boom")

    with trace_file.open("a", encoding="utf-8") as file:
        file.write("\n")
        file.write(
            json.dumps(
                {
                    "record_type": "event",
                    "trace_id": "trace-export",
                    "event_name": "autoglm.step",
                }
            )
        )
        file.write("\n")
        file.write(
            json.dumps(
                {
                    "schema": "autoglm.trace.span.v1",
                    "record_type": "span",
                    "trace_id": "trace-export",
                    "span_id": "manual-span",
                    "parent_span_id": None,
                    "name": "tool.call",
                    "status": "ok",
                    "start_time": "not-a-timestamp",
                    "end_time": None,
                    "duration_ms": 0,
                    "attrs": {"ratio": 1.5},
                }
            )
        )
        file.write("\n")

    exported = export_otlp_jsonl(trace_file, output_file, trace_id="trace-export")
    assert exported == 3
    otlp_records = [
        json.loads(line) for line in output_file.read_text().splitlines() if line
    ]
    spans = [
        item["resourceSpans"][0]["scopeSpans"][0]["spans"][0] for item in otlp_records
    ]
    span_by_name = {span["name"]: span for span in spans}
    llm_span = span_by_name["step.llm"]
    action_span = span_by_name["action.execute"]
    tool_span = span_by_name["tool.call"]
    assert llm_span["traceId"] == "trace-export"
    assert llm_span["status"]["code"] == 1
    assert action_span["status"]["code"] == 2
    attrs = {item["key"]: item["value"] for item in llm_span["attributes"]}
    assert attrs["openinference.span.kind"]["stringValue"] == "LLM"
    assert attrs["gen_ai.request.model"]["stringValue"] == "mock-model"
    tool_attrs = {item["key"]: item["value"] for item in tool_span["attributes"]}
    assert tool_attrs["ratio"]["doubleValue"] == 1.5
    assert tool_attrs["openinference.span.kind"]["stringValue"] == "TOOL"
    assert "startTimeUnixNano" not in tool_span
    assert "endTimeUnixNano" not in tool_span
