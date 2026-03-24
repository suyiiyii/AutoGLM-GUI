"""Contract tests for layered agent compatibility endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.layered_agent as layered_agent_api

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeTaskStore:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, object]] = {}
        self.events: dict[str, list[dict[str, object]]] = {}
        self.layered_session = {
            "id": "layered-session-1",
            "kind": "chat",
            "mode": "layered",
            "device_id": "device-1",
            "device_serial": "serial-1",
            "status": "open",
            "created_at": "2026-01-03T10:00:00",
            "updated_at": "2026-01-03T10:00:00",
        }

    def get_latest_open_chat_session(
        self, *, device_id: str, device_serial: str, mode: str = "classic"
    ) -> dict[str, object] | None:
        _ = device_serial
        if device_id == "device-1" and mode == "layered":
            return self.layered_session
        return None

    def get_task(self, task_id: str) -> dict[str, object] | None:
        return self.tasks.get(task_id)

    def list_task_events(
        self, task_id: str, *, after_seq: int = 0, **_: object
    ) -> list[dict[str, object]]:
        return [
            event
            for event in self.events.get(task_id, [])
            if int(event["seq"]) > after_seq
        ]

    def get_latest_active_session_task(
        self, session_id: str
    ) -> dict[str, object] | None:
        for task in self.tasks.values():
            if task["session_id"] == session_id and task["status"] in {
                "QUEUED",
                "RUNNING",
            }:
                return task
        return None


class FakeTaskManager:
    def __init__(self, store: FakeTaskStore) -> None:
        self.store = store
        self.cancelled_ids: list[str] = []
        self.archived_ids: list[str] = []
        self.waited_task_ids: list[str] = []

    async def get_session(self, session_id: str) -> dict[str, object] | None:
        if session_id == self.store.layered_session["id"]:
            return self.store.layered_session
        return None

    async def get_or_create_legacy_chat_session(
        self,
        *,
        device_id: str,
        device_serial: str,
        mode: str = "classic",
    ) -> dict[str, object]:
        assert device_id == "device-1"
        assert device_serial == "serial-1"
        assert mode == "layered"
        return self.store.layered_session

    async def submit_chat_task(
        self,
        *,
        session_id: str,
        device_id: str,
        device_serial: str,
        message: str,
    ) -> dict[str, object]:
        _ = (device_id, device_serial, message)
        task = {
            "id": "task-1",
            "session_id": session_id,
            "status": "SUCCEEDED",
        }
        self.store.tasks["task-1"] = task
        self.store.events["task-1"] = [
            {
                "task_id": "task-1",
                "seq": 1,
                "event_type": "tool_call",
                "role": "assistant",
                "payload": {"tool_name": "chat", "tool_args": {"device_id": "dev"}},
                "created_at": "2026-01-03T10:00:01",
            },
            {
                "task_id": "task-1",
                "seq": 2,
                "event_type": "message",
                "role": "assistant",
                "payload": {"content": "处理中"},
                "created_at": "2026-01-03T10:00:02",
            },
            {
                "task_id": "task-1",
                "seq": 3,
                "event_type": "done",
                "role": "assistant",
                "payload": {"content": "任务完成", "success": True},
                "created_at": "2026-01-03T10:00:03",
            },
        ]
        return task

    async def cancel_task(self, task_id: str) -> dict[str, object] | None:
        self.cancelled_ids.append(task_id)
        task = self.store.tasks.get(task_id)
        if task is not None:
            task["status"] = "CANCELLED"
        return task

    async def wait_for_task(
        self, task_id: str, timeout: float | None = None
    ) -> dict[str, object] | None:
        _ = timeout
        self.waited_task_ids.append(task_id)
        return self.store.tasks.get(task_id)

    async def archive_session(self, session_id: str) -> dict[str, object] | None:
        self.archived_ids.append(session_id)
        if session_id == self.store.layered_session["id"]:
            self.store.layered_session["status"] = "archived"
            return self.store.layered_session
        return None


@pytest.fixture
def layered_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store = FakeTaskStore()
    manager = FakeTaskManager(store)
    reset_calls: list[str] = []

    monkeypatch.setattr(layered_agent_api, "task_store", store)
    monkeypatch.setattr(layered_agent_api, "task_manager", manager)
    monkeypatch.setattr(
        layered_agent_api, "_resolve_device_serial", lambda _: "serial-1"
    )
    monkeypatch.setattr(
        layered_agent_api,
        "reset_layered_session",
        lambda session_id: reset_calls.append(session_id) or True,
    )

    app = FastAPI()
    app.include_router(layered_agent_api.router)

    return {
        "client": TestClient(app),
        "store": store,
        "manager": manager,
        "reset_calls": reset_calls,
    }


def test_chat_endpoint_streams_task_events(layered_env: dict[str, Any]) -> None:
    response = layered_env["client"].post(
        "/api/layered-agent/chat",
        json={"device_id": "device-1", "message": "复杂任务"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "tool_call"' in response.text
    assert '"type": "message"' in response.text
    assert '"type": "done"' in response.text
    assert "任务完成" in response.text


def test_chat_endpoint_supports_legacy_session_id_only_calls(
    layered_env: dict[str, Any],
) -> None:
    response = layered_env["client"].post(
        "/api/layered-agent/chat",
        json={"session_id": "device-1", "message": "复杂任务"},
    )

    assert response.status_code == 200
    assert '"type": "done"' in response.text


def test_abort_session_success(layered_env: dict[str, Any]) -> None:
    layered_env["store"].tasks["task-2"] = {
        "id": "task-2",
        "session_id": "layered-session-1",
        "status": "RUNNING",
    }

    response = layered_env["client"].post(
        "/api/layered-agent/abort",
        json={"session_id": "device-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Session device-1 abort signal sent",
    }
    assert layered_env["manager"].cancelled_ids == ["task-2"]


def test_abort_session_not_found(layered_env: dict[str, Any]) -> None:
    response = layered_env["client"].post(
        "/api/layered-agent/abort",
        json={"session_id": "missing-session"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "No active run found for session missing-session",
    }


def test_reset_session_clears_existing_session(layered_env: dict[str, Any]) -> None:
    layered_env["store"].tasks["task-2"] = {
        "id": "task-2",
        "session_id": "layered-session-1",
        "status": "RUNNING",
    }

    response = layered_env["client"].post(
        "/api/layered-agent/reset",
        json={"session_id": "device-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Session device-1 cleared",
    }
    assert layered_env["reset_calls"] == ["layered-session-1"]
    assert layered_env["manager"].archived_ids == ["layered-session-1"]
    assert layered_env["manager"].waited_task_ids == ["task-2"]


def test_reset_session_is_idempotent(layered_env: dict[str, Any]) -> None:
    response = layered_env["client"].post(
        "/api/layered-agent/reset",
        json={"session_id": "unknown-session"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Session unknown-session not found (already empty)",
    }
