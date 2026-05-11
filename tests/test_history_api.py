"""Contract tests for history API endpoints."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.history as history_api
from AutoGLM_GUI.models.history import (
    ConversationRecord,
    MessageRecord,
    StepTimingRecord,
    TraceSummaryRecord,
)

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeHistoryManager:
    def __init__(self) -> None:
        first = ConversationRecord(
            id="rec-1",
            task_text="点击消息",
            final_message="完成",
            success=True,
            steps=2,
            start_time=datetime(2026, 1, 1, 8, 0, 0),
            end_time=datetime(2026, 1, 1, 8, 0, 2),
            duration_ms=2000,
            source="chat",
            source_detail="",
            trace_id="trace-1",
            step_timings=[
                StepTimingRecord(
                    step=1,
                    trace_id="trace-1",
                    total_duration_ms=1200.0,
                    llm_duration_ms=800.0,
                    execute_action_duration_ms=200.0,
                    sleep_duration_ms=50.0,
                )
            ],
            trace_summary=TraceSummaryRecord(
                trace_id="trace-1",
                steps=2,
                total_duration_ms=2000.0,
                llm_duration_ms=1200.0,
                execute_action_duration_ms=300.0,
                sleep_duration_ms=80.0,
            ),
            messages=[
                MessageRecord(
                    role="user",
                    content="点击消息",
                    timestamp=datetime(2026, 1, 1, 8, 0, 0),
                ),
                MessageRecord(
                    role="assistant",
                    content="",
                    timestamp=datetime(2026, 1, 1, 8, 0, 1),
                    thinking="先点底部按钮",
                    action={"action": "Tap", "element": [100, 200]},
                    step=1,
                ),
            ],
        )

        second = ConversationRecord(
            id="rec-2",
            task_text="打开微信",
            final_message="失败",
            success=False,
            steps=1,
            start_time=datetime(2026, 1, 2, 9, 0, 0),
            end_time=datetime(2026, 1, 2, 9, 0, 1),
            duration_ms=1000,
            source="scheduled",
            source_detail="morning",
            error_message="Device offline",
            messages=[],
        )

        self.records: dict[str, list[ConversationRecord]] = {
            "device-1": [first, second],
        }

    def list_records(
        self, serialno: str, limit: int = 50, offset: int = 0
    ) -> list[ConversationRecord]:
        return self.records.get(serialno, [])[offset : offset + limit]

    def get_total_count(self, serialno: str) -> int:
        return len(self.records.get(serialno, []))

    def get_record(self, serialno: str, record_id: str) -> ConversationRecord | None:
        return next(
            (
                record
                for record in self.records.get(serialno, [])
                if record.id == record_id
            ),
            None,
        )

    def delete_record(self, serialno: str, record_id: str) -> bool:
        before = len(self.records.get(serialno, []))
        self.records[serialno] = [
            record
            for record in self.records.get(serialno, [])
            if record.id != record_id
        ]
        return len(self.records[serialno]) < before

    def clear_device_history(self, serialno: str) -> bool:
        existed = serialno in self.records and bool(self.records[serialno])
        self.records[serialno] = []
        return existed


class FakeTaskStore:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, object]] = {}
        self.events: dict[str, list[dict[str, object]]] = {}

    def list_tasks(
        self,
        *,
        device_serial: str | None = None,
        limit: int = 50,
        offset: int = 0,
        **_: object,
    ) -> tuple[list[dict[str, object]], int]:
        records = [
            task
            for task in self.tasks.values()
            if device_serial is None or task["device_serial"] == device_serial
        ]
        records.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return records[offset : offset + limit], len(records)

    def get_task(self, task_id: str) -> dict[str, object] | None:
        return self.tasks.get(task_id)

    def list_task_events(self, task_id: str) -> list[dict[str, object]]:
        return self.events.get(task_id, [])

    def delete_task(self, task_id: str) -> bool:
        existed = task_id in self.tasks
        self.tasks.pop(task_id, None)
        self.events.pop(task_id, None)
        return existed

    def clear_device_history(self, serialno: str) -> int:
        to_delete = [
            task_id
            for task_id, task in self.tasks.items()
            if task["device_serial"] == serialno
        ]
        for task_id in to_delete:
            self.delete_task(task_id)
        return len(to_delete)


@pytest.fixture
def fake_history_manager() -> FakeHistoryManager:
    return FakeHistoryManager()


@pytest.fixture
def fake_task_store() -> FakeTaskStore:
    return FakeTaskStore()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    fake_history_manager: FakeHistoryManager,
    fake_task_store: FakeTaskStore,
) -> TestClient:
    monkeypatch.setattr(history_api, "history_manager", fake_history_manager)
    monkeypatch.setattr(history_api, "task_store", fake_task_store)

    app = FastAPI()
    app.include_router(history_api.router)
    return TestClient(app)


def test_list_history_returns_paginated_data(client: TestClient) -> None:
    response = client.get("/api/history/device-1", params={"limit": 1, "offset": 0})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert len(data["records"]) == 1
    assert data["records"][0]["id"] == "rec-2"
    assert data["records"][0]["source"] == "scheduled"
    assert data["records"][0]["error_message"] == "Device offline"


def test_history_includes_task_backed_records(
    client: TestClient, fake_task_store: FakeTaskStore
) -> None:
    fake_task_store.tasks["task-1"] = {
        "id": "task-1",
        "source": "chat",
        "executor_key": "classic_chat",
        "session_id": "session-1",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "SUCCEEDED",
        "input_text": "打开相册",
        "final_message": "已打开相册",
        "error_message": None,
        "step_count": 1,
        "created_at": "2026-01-03T09:00:00",
        "started_at": "2026-01-03T09:00:01",
        "finished_at": "2026-01-03T09:00:03",
    }
    fake_task_store.events["task-1"] = [
        {
            "task_id": "task-1",
            "seq": 1,
            "event_type": "step",
            "role": "assistant",
            "payload": {
                "step": 1,
                "thinking": "先点击图库图标",
                "action": {"action": "Tap", "element": [20, 30]},
            },
            "created_at": "2026-01-03T09:00:02",
        }
    ]

    response = client.get("/api/history/device-1")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["records"][0]["id"] == "task-1"
    assert data["records"][0]["messages"][1]["thinking"] == "先点击图库图标"
    assert data["records"][0]["source_detail"] == "session-1"


def test_history_excludes_active_task_records(
    client: TestClient, fake_task_store: FakeTaskStore
) -> None:
    fake_task_store.tasks["task-active"] = {
        "id": "task-active",
        "source": "chat",
        "executor_key": "classic_chat",
        "session_id": "session-2",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "RUNNING",
        "input_text": "继续执行",
        "final_message": None,
        "error_message": None,
        "step_count": 1,
        "created_at": "2026-01-04T09:00:00",
        "started_at": "2026-01-04T09:00:01",
        "finished_at": None,
    }

    response = client.get("/api/history/device-1")

    assert response.status_code == 200
    data = response.json()
    assert all(record["id"] != "task-active" for record in data["records"])


def test_list_history_filters_by_classic_mode(
    client: TestClient, fake_task_store: FakeTaskStore
) -> None:
    fake_task_store.tasks["classic-task"] = {
        "id": "classic-task",
        "source": "chat",
        "executor_key": "classic_chat",
        "session_id": "sess-c",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "SUCCEEDED",
        "input_text": "经典任务",
        "final_message": "完成",
        "error_message": None,
        "step_count": 3,
        "created_at": "2026-02-01T10:00:00",
        "started_at": "2026-02-01T10:00:01",
        "finished_at": "2026-02-01T10:00:05",
    }
    fake_task_store.tasks["layered-task"] = {
        "id": "layered-task",
        "source": "chat",
        "executor_key": "layered_chat",
        "session_id": "sess-l",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "SUCCEEDED",
        "input_text": "分层任务",
        "final_message": "完成",
        "error_message": None,
        "step_count": 6,
        "created_at": "2026-02-02T10:00:00",
        "started_at": "2026-02-02T10:00:01",
        "finished_at": "2026-02-02T10:00:30",
    }

    response = client.get("/api/history/device-1", params={"mode": "classic"})

    assert response.status_code == 200
    ids = {record["id"] for record in response.json()["records"]}
    assert "classic-task" in ids
    assert "layered-task" not in ids
    # legacy record rec-1 (source="chat") belongs to classic mode
    assert "rec-1" in ids
    # legacy record rec-2 (source="scheduled") is not a classic chat record
    assert "rec-2" not in ids


def test_list_history_filters_by_layered_mode(
    client: TestClient,
    fake_task_store: FakeTaskStore,
    fake_history_manager: FakeHistoryManager,
) -> None:
    fake_task_store.tasks["classic-task"] = {
        "id": "classic-task",
        "source": "chat",
        "executor_key": "classic_chat",
        "session_id": "sess-c",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "SUCCEEDED",
        "input_text": "经典任务",
        "final_message": "完成",
        "error_message": None,
        "step_count": 3,
        "created_at": "2026-02-01T10:00:00",
        "started_at": "2026-02-01T10:00:01",
        "finished_at": "2026-02-01T10:00:05",
    }
    fake_task_store.tasks["layered-task"] = {
        "id": "layered-task",
        "source": "chat",
        "executor_key": "layered_chat",
        "session_id": "sess-l",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "SUCCEEDED",
        "input_text": "分层任务",
        "final_message": "完成",
        "error_message": None,
        "step_count": 6,
        "created_at": "2026-02-02T10:00:00",
        "started_at": "2026-02-02T10:00:01",
        "finished_at": "2026-02-02T10:00:30",
    }
    fake_history_manager.records["device-1"].append(
        ConversationRecord(
            id="legacy-layered",
            task_text="旧分层任务",
            final_message="完成",
            success=True,
            steps=0,
            start_time=datetime(2026, 1, 3, 9, 0, 0),
            end_time=datetime(2026, 1, 3, 9, 0, 5),
            duration_ms=5000,
            source="layered",
            source_detail="sess-old",
            messages=[],
        )
    )

    response = client.get("/api/history/device-1", params={"mode": "layered"})

    assert response.status_code == 200
    ids = {record["id"] for record in response.json()["records"]}
    assert "layered-task" in ids
    assert "legacy-layered" in ids
    assert "classic-task" not in ids
    assert "rec-1" not in ids
    assert "rec-2" not in ids


def test_list_history_rejects_invalid_mode(client: TestClient) -> None:
    response = client.get("/api/history/device-1", params={"mode": "bogus"})

    assert response.status_code == 400
    assert response.json()["detail"] == "mode must be 'classic' or 'layered'"


def test_history_converts_layered_tool_events_to_messages(
    client: TestClient, fake_task_store: FakeTaskStore
) -> None:
    fake_task_store.tasks["layered-task"] = {
        "id": "layered-task",
        "source": "chat",
        "executor_key": "layered_chat",
        "session_id": "sess-l",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "SUCCEEDED",
        "input_text": "整理桌面",
        "final_message": "已完成",
        "error_message": None,
        "step_count": 7,
        "created_at": "2026-02-05T10:00:00",
        "started_at": "2026-02-05T10:00:01",
        "finished_at": "2026-02-05T10:00:30",
    }
    fake_task_store.events["layered-task"] = [
        {
            "task_id": "layered-task",
            "seq": 1,
            "event_type": "tool_call",
            "role": "assistant",
            "payload": {
                "tool_name": "chat",
                "tool_args": {"device_id": "dev-1", "message": "打开设置"},
            },
            "created_at": "2026-02-05T10:00:05",
        },
        {
            "task_id": "layered-task",
            "seq": 2,
            "event_type": "tool_result",
            "role": "assistant",
            "payload": {
                "tool_name": "chat",
                "result": "已打开设置",
                "steps": 4,
                "success": True,
            },
            "created_at": "2026-02-05T10:00:15",
        },
        {
            "task_id": "layered-task",
            "seq": 3,
            "event_type": "message",
            "role": "assistant",
            "payload": {"content": "继续下一步"},
            "created_at": "2026-02-05T10:00:16",
        },
        {
            "task_id": "layered-task",
            "seq": 4,
            "event_type": "done",
            "role": "assistant",
            "payload": {"message": "已完成", "steps": 7, "success": True},
            "created_at": "2026-02-05T10:00:30",
        },
    ]

    response = client.get("/api/history/device-1/layered-task")

    assert response.status_code == 200
    data = response.json()
    assert data["steps"] == 7
    messages = data["messages"]
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "整理桌面"
    tool_call_messages = [message for message in messages if message.get("action")]
    assert any(
        message["action"].get("tool_name") == "chat" for message in tool_call_messages
    )
    assert any("已打开设置" in (message.get("content") or "") for message in messages)
    assert any(message.get("content") == "继续下一步" for message in messages)


def test_list_history_validates_limit_and_offset(client: TestClient) -> None:
    limit_response = client.get("/api/history/device-1", params={"limit": 101})
    assert limit_response.status_code == 400
    assert limit_response.json()["detail"] == "limit must be between 1 and 100"

    offset_response = client.get("/api/history/device-1", params={"offset": -1})
    assert offset_response.status_code == 400
    assert offset_response.json()["detail"] == "offset must be non-negative"


def test_get_history_record_success(client: TestClient) -> None:
    response = client.get("/api/history/device-1/rec-1")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "rec-1"
    assert data["messages"][1]["thinking"] == "先点底部按钮"
    assert data["messages"][1]["action"] == {"action": "Tap", "element": [100, 200]}
    assert data["trace_summary"]["trace_id"] == "trace-1"


def test_get_history_record_not_found(client: TestClient) -> None:
    response = client.get("/api/history/device-1/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Record not found"


def test_delete_history_record_success_and_not_found(client: TestClient) -> None:
    ok_resp = client.delete("/api/history/device-1/rec-2")
    assert ok_resp.status_code == 200
    assert ok_resp.json() == {"success": True, "message": "Record deleted"}

    missing_resp = client.delete("/api/history/device-1/rec-2")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["detail"] == "Record not found"


def test_delete_history_record_rejects_active_task(
    client: TestClient, fake_task_store: FakeTaskStore
) -> None:
    fake_task_store.tasks["task-active"] = {
        "id": "task-active",
        "source": "chat",
        "executor_key": "classic_chat",
        "session_id": "session-2",
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "dev-1",
        "device_serial": "device-1",
        "status": "RUNNING",
        "input_text": "继续执行",
        "final_message": None,
        "error_message": None,
        "step_count": 1,
        "created_at": "2026-01-04T09:00:00",
        "started_at": "2026-01-04T09:00:01",
        "finished_at": None,
    }

    response = client.delete("/api/history/device-1/task-active")

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Cannot delete task history while task is still active"
    )
    assert "task-active" in fake_task_store.tasks


def test_clear_history_always_returns_success_message(client: TestClient) -> None:
    response = client.delete("/api/history/device-1")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "History cleared for device-1",
    }
