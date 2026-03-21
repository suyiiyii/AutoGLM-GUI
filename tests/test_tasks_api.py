"""Contract tests for the task session and task APIs."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.tasks as tasks_api

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeTaskStore:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, object]] = {
            "task-1": {
                "id": "task-1",
                "source": "chat",
                "executor_key": "classic_chat",
                "session_id": "session-1",
                "scheduled_task_id": None,
                "workflow_uuid": None,
                "schedule_fire_id": None,
                "device_id": "device-1",
                "device_serial": "serial-1",
                "status": "SUCCEEDED",
                "input_text": "打开设置",
                "final_message": "已打开设置",
                "error_message": None,
                "step_count": 1,
                "created_at": "2026-01-01T08:00:00",
                "started_at": "2026-01-01T08:00:01",
                "finished_at": "2026-01-01T08:00:03",
            },
            "task-2": {
                "id": "task-2",
                "source": "scheduled",
                "executor_key": "scheduled_workflow",
                "session_id": None,
                "scheduled_task_id": "scheduled-1",
                "workflow_uuid": "wf-1",
                "schedule_fire_id": "fire-1",
                "device_id": "device-2",
                "device_serial": "serial-2",
                "status": "RUNNING",
                "input_text": "自动签到",
                "final_message": None,
                "error_message": None,
                "step_count": 0,
                "created_at": "2026-01-02T09:00:00",
                "started_at": "2026-01-02T09:00:01",
                "finished_at": None,
            },
        }
        self.events: dict[str, list[dict[str, object]]] = {
            "task-1": [
                {
                    "task_id": "task-1",
                    "seq": 1,
                    "event_type": "step",
                    "role": "assistant",
                    "payload": {"step": 1, "thinking": "先点击设置图标"},
                    "created_at": "2026-01-01T08:00:02",
                },
                {
                    "task_id": "task-1",
                    "seq": 2,
                    "event_type": "done",
                    "role": "assistant",
                    "payload": {
                        "message": "已打开设置",
                        "steps": 1,
                        "success": True,
                    },
                    "created_at": "2026-01-01T08:00:03",
                },
            ],
            "task-2": [
                {
                    "task_id": "task-2",
                    "seq": 1,
                    "event_type": "step",
                    "role": "assistant",
                    "payload": {"step": 1, "thinking": "正在打开应用"},
                    "created_at": "2026-01-02T09:00:02",
                }
            ],
        }

    def list_session_tasks(
        self, session_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, object]], int]:
        tasks = [
            task for task in self.tasks.values() if task["session_id"] == session_id
        ]
        tasks.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return tasks[offset : offset + limit], len(tasks)

    def list_tasks(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        device_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        **_: object,
    ) -> tuple[list[dict[str, object]], int]:
        tasks = list(self.tasks.values())
        if status is not None:
            tasks = [task for task in tasks if task["status"] == status]
        if source is not None:
            tasks = [task for task in tasks if task["source"] == source]
        if device_id is not None:
            tasks = [task for task in tasks if task["device_id"] == device_id]
        if session_id is not None:
            tasks = [task for task in tasks if task["session_id"] == session_id]
        tasks.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return tasks[offset : offset + limit], len(tasks)

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


class FakeTaskManager:
    def __init__(self, store: FakeTaskStore) -> None:
        self.store = store
        self.sessions: dict[str, dict[str, object]] = {
            "session-1": {
                "id": "session-1",
                "kind": "chat",
                "mode": "classic",
                "device_id": "device-1",
                "device_serial": "serial-1",
                "status": "open",
                "created_at": "2026-01-01T07:59:00",
                "updated_at": "2026-01-01T08:00:03",
            }
        }

    async def create_chat_session(
        self, *, device_id: str, device_serial: str
    ) -> dict[str, object]:
        session = {
            "id": "session-2",
            "kind": "chat",
            "mode": "classic",
            "device_id": device_id,
            "device_serial": device_serial,
            "status": "open",
            "created_at": "2026-01-03T10:00:00",
            "updated_at": "2026-01-03T10:00:00",
        }
        self.sessions[str(session["id"])] = session
        return session

    async def get_session(self, session_id: str) -> dict[str, object] | None:
        return self.sessions.get(session_id)

    async def submit_chat_task(
        self,
        *,
        session_id: str,
        device_id: str,
        device_serial: str,
        message: str,
    ) -> dict[str, object]:
        task = {
            "id": "task-3",
            "source": "chat",
            "executor_key": "classic_chat",
            "session_id": session_id,
            "scheduled_task_id": None,
            "workflow_uuid": None,
            "schedule_fire_id": None,
            "device_id": device_id,
            "device_serial": device_serial,
            "status": "QUEUED",
            "input_text": message,
            "final_message": None,
            "error_message": None,
            "step_count": 0,
            "created_at": "2026-01-03T10:00:01",
            "started_at": None,
            "finished_at": None,
        }
        self.store.tasks[str(task["id"])] = task
        self.store.events[str(task["id"])] = []
        return task

    async def cancel_task(self, task_id: str) -> dict[str, object] | None:
        task = self.store.tasks.get(task_id)
        if task is None:
            return None
        task["status"] = "CANCELLED"
        task["final_message"] = "Task cancelled by user"
        task["error_message"] = "Task cancelled by user"
        task["finished_at"] = "2026-01-03T10:00:05"
        return task


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    store = FakeTaskStore()
    manager = FakeTaskManager(store)
    monkeypatch.setattr(tasks_api, "task_store", store)
    monkeypatch.setattr(tasks_api, "task_manager", manager)

    app = FastAPI()
    app.include_router(tasks_api.router)
    return TestClient(app)


def test_task_session_create_and_submit(client: TestClient) -> None:
    create_resp = client.post(
        "/api/task-sessions",
        json={"device_id": "device-9", "device_serial": "serial-9"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["id"] == "session-2"

    session_resp = client.get("/api/task-sessions/session-1")
    assert session_resp.status_code == 200
    assert session_resp.json()["device_id"] == "device-1"

    submit_resp = client.post(
        "/api/task-sessions/session-1/tasks",
        json={"message": "打开相册"},
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["id"] == "task-3"
    assert submit_resp.json()["status"] == "QUEUED"


def test_task_list_endpoints_support_filters(client: TestClient) -> None:
    session_tasks = client.get("/api/task-sessions/session-1/tasks")
    assert session_tasks.status_code == 200
    assert session_tasks.json()["total"] == 1
    assert session_tasks.json()["tasks"][0]["id"] == "task-1"

    filtered = client.get("/api/tasks", params={"source": "scheduled"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["tasks"][0]["id"] == "task-2"


def test_task_detail_and_events(client: TestClient) -> None:
    task_resp = client.get("/api/tasks/task-1")
    assert task_resp.status_code == 200
    assert task_resp.json()["final_message"] == "已打开设置"

    events_resp = client.get("/api/tasks/task-1/events", params={"after_seq": 1})
    assert events_resp.status_code == 200
    assert len(events_resp.json()["events"]) == 1
    assert events_resp.json()["events"][0]["event_type"] == "done"


def test_task_stream_and_cancel(client: TestClient) -> None:
    stream_resp = client.get("/api/tasks/task-1/stream")
    assert stream_resp.status_code == 200
    assert stream_resp.headers["content-type"].startswith("text/event-stream")
    assert "event: step" in stream_resp.text
    assert '"message": "已打开设置"' in stream_resp.text

    cancel_resp = client.post("/api/tasks/task-2/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["success"] is True
    assert cancel_resp.json()["task"]["status"] == "CANCELLED"
