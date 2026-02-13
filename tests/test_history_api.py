"""Contract tests for history API endpoints."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.history as history_api
from AutoGLM_GUI.models.history import ConversationRecord, MessageRecord

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


@pytest.fixture
def fake_history_manager() -> FakeHistoryManager:
    return FakeHistoryManager()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    fake_history_manager: FakeHistoryManager,
) -> TestClient:
    monkeypatch.setattr(history_api, "history_manager", fake_history_manager)

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
    assert data["records"][0]["id"] == "rec-1"


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


def test_clear_history_always_returns_success_message(client: TestClient) -> None:
    response = client.delete("/api/history/device-1")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "History cleared for device-1",
    }
