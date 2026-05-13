"""End-to-end coverage for trace replay files with mock LLM and device."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from AutoGLM_GUI.trace_export import export_otlp_jsonl
from tests.integration.test_task_system_e2e import (
    _configure_mock_llm,
    _register_remote_device,
    _wait_for_task_completion,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _wait_for_jsonl(
    path: Path,
    predicate: Callable[[list[dict[str, Any]]], bool],
    *,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    start = time.time()
    last_records: list[dict[str, Any]] = []
    while time.time() - start < timeout:
        if path.exists():
            last_records = _read_jsonl(path)
            if predicate(last_records):
                return last_records
        time.sleep(0.2)
    raise AssertionError(
        f"Timed out waiting for expected records in {path}: {last_records}"
    )


def _submit_trace_task(
    *,
    local_server: dict[str, Any],
    mock_agent_server: str,
    test_client: Any,
    sample_test_case: Path,
) -> tuple[dict[str, Any], str]:
    local_server["remote_url"] = mock_agent_server
    access_url = str(local_server["access_url"])
    remote_url = str(local_server["remote_url"])
    llm_url = str(local_server["llm_url"])

    test_client.load_scenario(str(sample_test_case))
    registered_device_id, registered_serial = _register_remote_device(
        access_url,
        remote_url,
    )
    _configure_mock_llm(access_url, llm_url)

    session_resp = httpx.post(
        f"{access_url}/api/task-sessions",
        json={
            "device_id": registered_device_id,
            "device_serial": registered_serial,
        },
        timeout=10,
    )
    assert session_resp.status_code == 200, (
        f"Failed to create task session: {session_resp.text}"
    )
    session_id = session_resp.json()["id"]

    submit_resp = httpx.post(
        f"{access_url}/api/task-sessions/{session_id}/tasks",
        json={"message": "点击屏幕下方的消息按钮"},
        timeout=10,
    )
    assert submit_resp.status_code == 200, f"Failed to submit task: {submit_resp.text}"
    task_id = submit_resp.json()["id"]

    final_task = _wait_for_task_completion(access_url, task_id, timeout=30.0)
    assert final_task["status"] == "SUCCEEDED"
    assert final_task["trace_id"]
    return final_task, registered_serial


@pytest.mark.integration
class TestTraceReplayE2E:
    """Validate replay trace behavior through the real local server stack."""

    def test_task_trace_replay_files_are_written_end_to_end(
        self,
        local_server: dict[str, Any],
        mock_llm_client,
        mock_agent_server: str,
        test_client,
        sample_test_case: Path,
    ) -> None:
        final_task, _ = _submit_trace_task(
            local_server=local_server,
            mock_agent_server=mock_agent_server,
            test_client=test_client,
            sample_test_case=sample_test_case,
        )
        trace_id = str(final_task["trace_id"])
        task_id = str(final_task["id"])
        trace_file = Path(local_server["trace_file"])
        replay_file = (
            Path(local_server["trace_root"]) / "runs" / trace_id / "replay.jsonl"
        )

        trace_records = _wait_for_jsonl(
            trace_file,
            lambda records: any(
                record.get("trace_id") == trace_id
                and record.get("name") == "task_store.task.finish"
                for record in records
            ),
        )
        task_trace_records = [
            record for record in trace_records if record.get("trace_id") == trace_id
        ]
        span_names = {record["name"] for record in task_trace_records}
        assert {
            "agent.step",
            "step.capture_screenshot",
            "step.llm",
            "step.execute_action",
            "task_store.event.append",
            "task_store.task.finish",
        } <= span_names
        assert all(
            record["schema"] == "autoglm.trace.span.v1" for record in task_trace_records
        )
        assert all(record["record_type"] == "span" for record in task_trace_records)

        replay_records = _wait_for_jsonl(
            replay_file,
            lambda records: {
                "autoglm.task.start",
                "autoglm.step",
                "autoglm.task.done",
                "autoglm.trace.summary",
                "autoglm.task.status",
            }
            <= {record.get("event_name") for record in records},
        )
        assert [record["event_seq"] for record in replay_records] == sorted(
            record["event_seq"] for record in replay_records
        )

        step_records = [
            record
            for record in replay_records
            if record["event_name"] == "autoglm.step"
        ]
        assert len(step_records) == final_task["step_count"]
        first_step = step_records[0]["step"]
        assert "消息按钮" in first_step["thinking"]
        assert first_step["action"]["action"] == "Tap"
        assert first_step["timings"]["llm_duration_ms"] > 0
        screenshot_ref = first_step["artifacts"]["screenshot"]
        screenshot_path = replay_file.parent / screenshot_ref["path"]
        assert screenshot_path.exists()
        assert screenshot_path.stat().st_size > 0

        events_resp = httpx.get(
            f"{local_server['access_url']}/api/tasks/{task_id}/events",
            timeout=10,
        )
        assert events_resp.status_code == 200
        api_step = next(
            event
            for event in events_resp.json()["events"]
            if event["event_type"] == "step"
        )
        screenshot_base64 = api_step["payload"]["screenshot"]
        assert isinstance(screenshot_base64, str)
        assert screenshot_base64
        assert screenshot_base64 not in json.dumps(first_step, ensure_ascii=False)

        otlp_file = Path(local_server["trace_root"]) / "trace.otlp.jsonl"
        exported = export_otlp_jsonl(trace_file, otlp_file, trace_id=trace_id)
        assert exported > 0
        otlp_records = _read_jsonl(otlp_file)
        otlp_spans = [
            span
            for item in otlp_records
            for resource_span in item["resourceSpans"]
            for scope_span in resource_span["scopeSpans"]
            for span in scope_span["spans"]
        ]
        llm_span = next(span for span in otlp_spans if span["name"] == "step.llm")
        llm_attrs = {item["key"]: item["value"] for item in llm_span["attributes"]}
        assert llm_attrs["openinference.span.kind"]["stringValue"] == "LLM"
        assert llm_attrs["gen_ai.operation.name"]["stringValue"] == "chat"
        mock_llm_client.assert_request_count(2)

    def test_history_delete_removes_replay_run_end_to_end(
        self,
        local_server: dict[str, Any],
        mock_agent_server: str,
        test_client,
        sample_test_case: Path,
    ) -> None:
        final_task, registered_serial = _submit_trace_task(
            local_server=local_server,
            mock_agent_server=mock_agent_server,
            test_client=test_client,
            sample_test_case=sample_test_case,
        )
        trace_id = str(final_task["trace_id"])
        task_id = str(final_task["id"])
        replay_dir = Path(local_server["trace_root"]) / "runs" / trace_id
        replay_file = replay_dir / "replay.jsonl"

        _wait_for_jsonl(
            replay_file,
            lambda records: any(
                record.get("event_name") == "autoglm.trace.summary"
                for record in records
            ),
        )
        assert replay_dir.exists()

        delete_resp = httpx.delete(
            f"{local_server['access_url']}/api/history/{registered_serial}/{task_id}",
            timeout=10,
        )
        assert delete_resp.status_code == 200, delete_resp.text
        assert not replay_dir.exists()
