"""Tests for Phase 1: Task API productisation — status validation, enum typing,
duration_ms computation, and device_serial filter."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.tasks as tasks_api
from AutoGLM_GUI.schemas import TaskRunResponse, TaskSessionResponse
from AutoGLM_GUI.task_store import TaskSessionStatus, TaskStatus


pytestmark = [pytest.mark.contract]


# ---------------------------------------------------------------------------
# Schema enum typing
# ---------------------------------------------------------------------------


def test_task_run_response_accepts_task_status_enum() -> None:
    """TaskRunResponse.status should accept TaskStatus enum values."""
    resp = TaskRunResponse(
        id="t1",
        source="chat",
        executor_key="classic_chat",
        device_id="d1",
        device_serial="s1",
        status=TaskStatus.RUNNING,
        input_text="hello",
        final_message=None,
        error_message=None,
        step_count=0,
        created_at="2026-01-01T00:00:00Z",
    )
    assert resp.status == TaskStatus.RUNNING
    data = resp.model_dump()
    assert data["status"] == "RUNNING"


def test_task_run_response_accepts_string_status() -> None:
    """TaskRunResponse.status should also accept plain strings for backward compat."""
    resp = TaskRunResponse(
        id="t1",
        source="chat",
        executor_key="classic_chat",
        device_id="d1",
        device_serial="s1",
        status="RUNNING",
        input_text="hello",
        final_message=None,
        error_message=None,
        step_count=0,
        created_at="2026-01-01T00:00:00Z",
    )
    assert resp.status == TaskStatus.RUNNING


def test_task_session_response_uses_session_status_enum() -> None:
    """TaskSessionResponse.status should be TaskSessionStatus."""
    resp = TaskSessionResponse(
        id="s1",
        kind="chat",
        mode="classic",
        device_id="d1",
        device_serial="s1",
        status=TaskSessionStatus.OPEN,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    assert resp.status == TaskSessionStatus.OPEN
    data = resp.model_dump()
    assert data["status"] == "open"


def test_task_run_response_includes_duration_ms() -> None:
    """TaskRunResponse should include duration_ms field."""
    resp = TaskRunResponse(
        id="t1",
        source="chat",
        executor_key="classic_chat",
        device_id="d1",
        device_serial="s1",
        status=TaskStatus.SUCCEEDED,
        input_text="hello",
        final_message="done",
        error_message=None,
        step_count=3,
        created_at="2026-01-01T00:00:00Z",
        duration_ms=5000,
    )
    assert resp.duration_ms == 5000


def test_task_run_response_duration_ms_default_none() -> None:
    """duration_ms should default to None when not provided."""
    resp = TaskRunResponse(
        id="t1",
        source="chat",
        executor_key="classic_chat",
        device_id="d1",
        device_serial="s1",
        status=TaskStatus.QUEUED,
        input_text="hello",
        final_message=None,
        error_message=None,
        step_count=0,
        created_at="2026-01-01T00:00:00Z",
    )
    assert resp.duration_ms is None


# ---------------------------------------------------------------------------
# Helper function: _task_run_response computes duration_ms
# ---------------------------------------------------------------------------


def test_task_run_response_helper_computes_duration() -> None:
    """The _task_run_response helper should compute duration_ms from
    started_at/finished_at timestamps."""
    record = {
        "id": "t1",
        "source": "chat",
        "executor_key": "classic_chat",
        "session_id": None,
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "d1",
        "device_serial": "s1",
        "status": "SUCCEEDED",
        "input_text": "hello",
        "final_message": "done",
        "error_message": None,
        "step_count": 3,
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:02.500+00:00",
    }
    resp = tasks_api._task_run_response(record)
    assert resp.duration_ms == 2500
    assert resp.status == TaskStatus.SUCCEEDED


def test_task_run_response_helper_duration_none_without_finished() -> None:
    """duration_ms should be None when finished_at is missing."""
    record = {
        "id": "t1",
        "source": "chat",
        "executor_key": "classic_chat",
        "session_id": None,
        "scheduled_task_id": None,
        "workflow_uuid": None,
        "schedule_fire_id": None,
        "device_id": "d1",
        "device_serial": "s1",
        "status": "RUNNING",
        "input_text": "hello",
        "final_message": None,
        "error_message": None,
        "step_count": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": None,
    }
    resp = tasks_api._task_run_response(record)
    assert resp.duration_ms is None


# ---------------------------------------------------------------------------
# API-level: status validation and device_serial filter
# ---------------------------------------------------------------------------
# Reuse the FakeTaskStore / FakeTaskManager pattern from test_tasks_api.py


class _FakeTaskStore:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, object]] = {}
        self.events: dict[str, list[dict[str, object]]] = {}

    def list_tasks(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        device_id: str | None = None,
        device_serial: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        **_: object,
    ) -> tuple[list[dict[str, object]], int]:
        return [], 0

    def get_task(self, task_id: str) -> dict[str, object] | None:
        return None

    def list_task_events(
        self, task_id: str, *, after_seq: int = 0, **_: object
    ) -> list[dict[str, object]]:
        return []


class _FakeTaskManager:
    pass


@pytest.fixture
def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    store = _FakeTaskStore()
    manager = _FakeTaskManager()
    monkeypatch.setattr(tasks_api, "task_store", store)
    monkeypatch.setattr(tasks_api, "task_manager", manager)
    app = FastAPI()
    app.include_router(tasks_api.router)
    return TestClient(app)


def test_list_tasks_rejects_invalid_status(_client: TestClient) -> None:
    """GET /api/tasks?status=INVALID should return 422."""
    response = _client.get("/api/tasks?status=INVALID")
    assert response.status_code == 422
    assert "Invalid status" in response.json()["detail"]


def test_list_tasks_accepts_valid_status(_client: TestClient) -> None:
    """GET /api/tasks?status=RUNNING should return 200."""
    response = _client.get("/api/tasks?status=RUNNING")
    assert response.status_code == 200


def test_list_tasks_accepts_device_serial_filter(_client: TestClient) -> None:
    """GET /api/tasks?device_serial=abc should return 200 (filter accepted)."""
    response = _client.get("/api/tasks?device_serial=abc123")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "valid_status",
    ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"],
)
def test_list_tasks_accepts_all_valid_statuses(
    _client: TestClient, valid_status: str
) -> None:
    """All TaskStatus values should be accepted as filter."""
    response = _client.get(f"/api/tasks?status={valid_status}")
    assert response.status_code == 200
