"""Local end-to-end tests for the new Task system APIs."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest


def _register_remote_device(access_url: str, remote_url: str) -> tuple[str, str]:
    """Register the mock remote device and return device_id and serial."""
    try:
        resp = httpx.get(f"{access_url}/api/devices", timeout=10)
        if resp.status_code == 200:
            devices = resp.json()["devices"]
            for device in devices:
                if device.get("model") == "mock_device_001":
                    httpx.delete(
                        f"{access_url}/api/devices/{device['id']}",
                        timeout=10,
                    )
    except Exception as exc:
        print(f"[Task E2E] Failed to cleanup devices: {exc}")

    resp = httpx.post(
        f"{access_url}/api/devices/add_remote",
        json={
            "base_url": remote_url,
            "device_id": "mock_device_001",
        },
        timeout=10,
    )
    assert resp.status_code == 200, f"Failed to register device: {resp.text}"

    register_result = resp.json()
    assert register_result["success"] is True, (
        f"Remote device registration failed: {register_result}"
    )
    registered_serial = register_result["serial"]

    resp = httpx.get(f"{access_url}/api/devices", timeout=10)
    assert resp.status_code == 200
    devices = resp.json()["devices"]
    remote_devices = [d for d in devices if d["serial"] == registered_serial]
    assert remote_devices, (
        f"Registered remote device {registered_serial} not found. "
        f"Available devices: {[d['serial'] for d in devices]}"
    )
    return remote_devices[0]["id"], registered_serial


def _configure_mock_llm(access_url: str, llm_url: str) -> None:
    """Point the local server at the mock LLM."""
    try:
        httpx.delete(f"{access_url}/api/config", timeout=10)
    except Exception as exc:
        print(f"[Task E2E] No config to delete: {exc}")

    resp = httpx.post(
        f"{access_url}/api/config",
        json={
            "base_url": llm_url + "/v1",
            "model_name": "mock-glm-model",
            "api_key": "mock-key",
        },
        timeout=10,
    )
    assert resp.status_code == 200, f"Failed to save config: {resp.text}"


def _wait_for_task_completion(
    access_url: str, task_id: str, timeout: float = 30.0
) -> dict:
    """Poll a task until it reaches a terminal state."""
    start = time.time()
    while time.time() - start < timeout:
        resp = httpx.get(f"{access_url}/api/tasks/{task_id}", timeout=10)
        assert resp.status_code == 200, f"Failed to fetch task: {resp.text}"
        task = resp.json()
        if task["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"}:
            return task
        time.sleep(0.2)
    raise AssertionError(f"Task {task_id} did not finish within {timeout}s")


@pytest.mark.integration
class TestTaskSystemE2E:
    """End-to-end tests that exercise the new Task APIs directly."""

    @pytest.mark.release_gate
    def test_task_session_chat_scenario(
        self,
        local_server: dict,
        mock_llm_client,
        mock_agent_server: str,
        test_client,
        sample_test_case: Path,
    ) -> None:
        local_server["remote_url"] = mock_agent_server
        access_url = local_server["access_url"]
        remote_url = local_server["remote_url"]
        llm_url = local_server["llm_url"]

        test_client.load_scenario(str(sample_test_case))
        registered_device_id, registered_serial = _register_remote_device(
            access_url,
            remote_url,
        )
        _configure_mock_llm(access_url, llm_url)

        instruction = "点击屏幕下方的消息按钮"
        print(f"[Task E2E] Creating task session for {registered_device_id}")
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
        session = session_resp.json()
        session_id = session["id"]
        assert session["kind"] == "chat"
        assert session["mode"] == "classic"
        assert session["device_id"] == registered_device_id
        assert session["device_serial"] == registered_serial

        session_detail_resp = httpx.get(
            f"{access_url}/api/task-sessions/{session_id}",
            timeout=10,
        )
        assert session_detail_resp.status_code == 200
        assert session_detail_resp.json()["id"] == session_id

        print(f"[Task E2E] Submitting task to session {session_id}")
        submit_resp = httpx.post(
            f"{access_url}/api/task-sessions/{session_id}/tasks",
            json={"message": instruction},
            timeout=10,
        )
        assert submit_resp.status_code == 200, (
            f"Failed to submit task: {submit_resp.text}"
        )
        task = submit_resp.json()
        task_id = task["id"]
        assert task["session_id"] == session_id
        assert task["source"] == "chat"
        assert task["executor_key"] == "classic_chat"
        assert task["status"] == "QUEUED"

        final_task = _wait_for_task_completion(access_url, task_id, timeout=30.0)
        print(f"[Task E2E] Final task result: {final_task}")
        assert final_task["status"] == "SUCCEEDED"
        assert final_task["step_count"] == 2
        assert final_task["final_message"]

        session_tasks_resp = httpx.get(
            f"{access_url}/api/task-sessions/{session_id}/tasks",
            timeout=10,
        )
        assert session_tasks_resp.status_code == 200
        session_tasks = session_tasks_resp.json()
        assert session_tasks["total"] >= 1
        assert any(item["id"] == task_id for item in session_tasks["tasks"])

        filtered_tasks_resp = httpx.get(
            f"{access_url}/api/tasks",
            params={"session_id": session_id},
            timeout=10,
        )
        assert filtered_tasks_resp.status_code == 200
        filtered_tasks = filtered_tasks_resp.json()
        assert any(item["id"] == task_id for item in filtered_tasks["tasks"])

        events_resp = httpx.get(
            f"{access_url}/api/tasks/{task_id}/events",
            timeout=10,
        )
        assert events_resp.status_code == 200
        events = events_resp.json()["events"]
        event_types = [event["event_type"] for event in events]
        assert "step" in event_types
        assert "done" in event_types

        stream_resp = httpx.get(
            f"{access_url}/api/tasks/{task_id}/stream",
            timeout=10,
        )
        assert stream_resp.status_code == 200
        assert stream_resp.headers["content-type"].startswith("text/event-stream")
        assert "event: step" in stream_resp.text
        assert "event: done" in stream_resp.text

        mock_llm_stats = mock_llm_client.get_stats()
        assert mock_llm_stats["request_count"] == 2, (
            f"Expected 2 LLM requests, got {mock_llm_stats['request_count']}"
        )

        commands = test_client.get_commands()
        tap_commands = [command for command in commands if command["action"] == "tap"]
        assert len(tap_commands) >= 1, (
            f"Expected at least 1 tap, got {len(tap_commands)}. All commands: {commands}"
        )

        tap = tap_commands[0]
        x, y = tap["params"]["x"], tap["params"]["y"]
        assert 487 <= x <= 721, f"Tap x={x} not in message button region [487, 721]"
        assert 2516 <= y <= 2667, f"Tap y={y} not in message button region [2516, 2667]"

        state = test_client.get_state()
        assert state["current_state"] == "message", (
            f"Expected state 'message', got '{state['current_state']}'"
        )

        print("[Task E2E] ✓ Task API end-to-end test passed!")

    @pytest.mark.release_gate
    def test_multi_turn_task_session_scenario(
        self,
        local_server: dict,
        mock_llm_client,
        mock_agent_server: str,
        test_client,
        sample_test_case: Path,
    ) -> None:
        """Verify multiple task runs can share the same task session."""
        local_server["remote_url"] = mock_agent_server
        access_url = local_server["access_url"]
        remote_url = local_server["remote_url"]
        llm_url = local_server["llm_url"]

        test_client.load_scenario(str(sample_test_case))
        registered_device_id, registered_serial = _register_remote_device(
            access_url,
            remote_url,
        )
        _configure_mock_llm(access_url, llm_url)

        mock_llm_client.set_responses(
            [
                """用户要求点击屏幕下方的消息按钮。我需要点击底部导航栏中的消息入口。
                do(action="Tap", element=[499,966])""",
                """好的，我已经进入消息页面。
                finish(message="已进入消息页面。")""",
                """我看到当前已经在消息页面，无需重复点击。
                finish(message="已确认当前仍在消息页面。")""",
            ]
        )

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

        first_submit_resp = httpx.post(
            f"{access_url}/api/task-sessions/{session_id}/tasks",
            json={"message": "点击屏幕下方的消息按钮"},
            timeout=10,
        )
        assert first_submit_resp.status_code == 200, (
            f"Failed to submit first task: {first_submit_resp.text}"
        )
        first_task_id = first_submit_resp.json()["id"]
        first_task = _wait_for_task_completion(access_url, first_task_id, timeout=30.0)
        assert first_task["status"] == "SUCCEEDED"
        assert first_task["final_message"] == "已进入消息页面。"

        state_after_first = test_client.get_state()
        assert state_after_first["current_state"] == "message", (
            f"Expected message state after first task, got {state_after_first['current_state']}"
        )

        second_submit_resp = httpx.post(
            f"{access_url}/api/task-sessions/{session_id}/tasks",
            json={"message": "确认当前是否仍然在消息页面"},
            timeout=10,
        )
        assert second_submit_resp.status_code == 200, (
            f"Failed to submit second task: {second_submit_resp.text}"
        )
        second_task_id = second_submit_resp.json()["id"]
        second_task = _wait_for_task_completion(
            access_url,
            second_task_id,
            timeout=30.0,
        )
        assert second_task["status"] == "SUCCEEDED"
        assert second_task["final_message"] == "已确认当前仍在消息页面。"
        assert second_task["session_id"] == session_id

        session_tasks_resp = httpx.get(
            f"{access_url}/api/task-sessions/{session_id}/tasks",
            timeout=10,
        )
        assert session_tasks_resp.status_code == 200
        session_tasks = session_tasks_resp.json()
        assert session_tasks["total"] == 2
        returned_ids = [task["id"] for task in session_tasks["tasks"]]
        assert second_task_id in returned_ids
        assert first_task_id in returned_ids

        second_events_resp = httpx.get(
            f"{access_url}/api/tasks/{second_task_id}/events",
            timeout=10,
        )
        assert second_events_resp.status_code == 200
        second_event_types = [
            event["event_type"] for event in second_events_resp.json()["events"]
        ]
        assert "done" in second_event_types

        mock_llm_stats = mock_llm_client.get_stats()
        assert mock_llm_stats["request_count"] == 3, (
            f"Expected 3 LLM requests across two turns, got {mock_llm_stats['request_count']}"
        )

        commands = test_client.get_commands()
        tap_commands = [command for command in commands if command["action"] == "tap"]
        assert len(tap_commands) == 1, (
            "Expected only the first turn to perform a tap; "
            f"got {len(tap_commands)} tap commands: {tap_commands}"
        )

        state_after_second = test_client.get_state()
        assert state_after_second["current_state"] == "message", (
            f"Expected message state after second task, got {state_after_second['current_state']}"
        )

        print("[Task E2E] ✓ Multi-turn task session test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
