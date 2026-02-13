"""Contract tests for scheduled task API endpoints."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.scheduled_tasks as scheduled_tasks_api
import AutoGLM_GUI.workflow_manager as workflow_manager_module
from AutoGLM_GUI.models.scheduled_task import ScheduledTask

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeWorkflowManager:
    def __init__(self) -> None:
        self.workflows: dict[str, dict[str, str]] = {
            "wf-1": {"uuid": "wf-1", "name": "Main", "text": "Do something"}
        }

    def get_workflow(self, workflow_uuid: str) -> dict[str, str] | None:
        return self.workflows.get(workflow_uuid)


class FakeSchedulerManager:
    def __init__(self) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.next_run_times: dict[str, datetime] = {}

    def list_tasks(self) -> list[ScheduledTask]:
        return list(self.tasks.values())

    def create_task(
        self,
        name: str,
        workflow_uuid: str,
        device_serialnos: list[str] | None,
        cron_expression: str,
        enabled: bool = True,
        device_group_id: str | None = None,
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            workflow_uuid=workflow_uuid,
            device_serialnos=device_serialnos or [],
            device_group_id=device_group_id,
            cron_expression=cron_expression,
            enabled=enabled,
        )
        self.tasks[task.id] = task
        if enabled:
            self.next_run_times[task.id] = datetime(2026, 1, 1, 8, 0, 0)
        return task

    def get_task(self, task_id: str) -> ScheduledTask | None:
        return self.tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs) -> ScheduledTask | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None

        old_enabled = task.enabled
        old_cron = task.cron_expression

        for key, value in kwargs.items():
            if value is not None and hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime(2026, 1, 1, 9, 0, 0)

        if old_enabled and not task.enabled:
            self.next_run_times.pop(task_id, None)
        elif not old_enabled and task.enabled:
            self.next_run_times[task_id] = datetime(2026, 1, 1, 10, 0, 0)
        elif task.enabled and old_cron != task.cron_expression:
            self.next_run_times[task_id] = datetime(2026, 1, 1, 10, 30, 0)

        return task

    def delete_task(self, task_id: str) -> bool:
        return self.tasks.pop(task_id, None) is not None

    def set_enabled(self, task_id: str, enabled: bool) -> bool:
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.enabled = enabled
        if enabled:
            self.next_run_times[task_id] = datetime(2026, 1, 1, 10, 0, 0)
        else:
            self.next_run_times.pop(task_id, None)
        return True

    def get_next_run_time(self, task_id: str) -> datetime | None:
        return self.next_run_times.get(task_id)


@pytest.fixture
def fake_workflow_manager() -> FakeWorkflowManager:
    return FakeWorkflowManager()


@pytest.fixture
def fake_scheduler_manager() -> FakeSchedulerManager:
    return FakeSchedulerManager()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    fake_workflow_manager: FakeWorkflowManager,
    fake_scheduler_manager: FakeSchedulerManager,
) -> TestClient:
    monkeypatch.setattr(
        workflow_manager_module, "workflow_manager", fake_workflow_manager
    )
    monkeypatch.setattr(
        scheduled_tasks_api, "scheduler_manager", fake_scheduler_manager
    )

    app = FastAPI()
    app.include_router(scheduled_tasks_api.router)
    return TestClient(app)


def _create_task(client: TestClient) -> dict:
    response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Morning",
            "workflow_uuid": "wf-1",
            "device_serialnos": ["dev-1", " dev-1 ", "dev-2"],
            "cron_expression": "0 8 * * *",
            "enabled": True,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_scheduled_task_success(client: TestClient) -> None:
    created = _create_task(client)

    assert created["name"] == "Morning"
    assert created["workflow_uuid"] == "wf-1"
    assert created["device_serialnos"] == ["dev-1", "dev-2"]
    assert created["cron_expression"] == "0 8 * * *"
    assert created["enabled"] is True
    assert created["next_run_time"] == "2026-01-01T08:00:00"


def test_create_scheduled_task_requires_existing_workflow(
    client: TestClient,
    fake_workflow_manager: FakeWorkflowManager,
) -> None:
    fake_workflow_manager.workflows.clear()

    response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Morning",
            "workflow_uuid": "wf-unknown",
            "device_serialnos": ["dev-1"],
            "cron_expression": "0 8 * * *",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Workflow not found"


def test_create_scheduled_task_validation_errors(client: TestClient) -> None:
    missing_target_resp = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Morning",
            "workflow_uuid": "wf-1",
            "cron_expression": "0 8 * * *",
        },
    )
    assert missing_target_resp.status_code == 422

    bad_cron_resp = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "Morning",
            "workflow_uuid": "wf-1",
            "device_serialnos": ["dev-1"],
            "cron_expression": "0 8 *",
        },
    )
    assert bad_cron_resp.status_code == 422


def test_list_and_get_scheduled_tasks(client: TestClient) -> None:
    created = _create_task(client)

    list_resp = client.get("/api/scheduled-tasks")
    assert list_resp.status_code == 200
    tasks = list_resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == created["id"]

    get_resp = client.get(f"/api/scheduled-tasks/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]


def test_get_scheduled_task_not_found(client: TestClient) -> None:
    response = client.get("/api/scheduled-tasks/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_update_scheduled_task_success(client: TestClient) -> None:
    created = _create_task(client)

    response = client.put(
        f"/api/scheduled-tasks/{created['id']}",
        json={"name": "Evening", "enabled": False},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Evening"
    assert updated["enabled"] is False
    assert updated["next_run_time"] is None


def test_update_scheduled_task_not_found(client: TestClient) -> None:
    response = client.put(
        "/api/scheduled-tasks/missing",
        json={"name": "Evening"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_delete_scheduled_task_success_and_not_found(client: TestClient) -> None:
    created = _create_task(client)

    ok_resp = client.delete(f"/api/scheduled-tasks/{created['id']}")
    assert ok_resp.status_code == 200
    assert ok_resp.json() == {"success": True, "message": "Task deleted"}

    missing_resp = client.delete(f"/api/scheduled-tasks/{created['id']}")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["detail"] == "Task not found"


def test_enable_disable_scheduled_task(client: TestClient) -> None:
    created = _create_task(client)
    task_id = created["id"]

    disable_resp = client.post(f"/api/scheduled-tasks/{task_id}/disable")
    assert disable_resp.status_code == 200
    assert disable_resp.json() == {"success": True, "message": "Task disabled"}

    enable_resp = client.post(f"/api/scheduled-tasks/{task_id}/enable")
    assert enable_resp.status_code == 200
    assert enable_resp.json() == {"success": True, "message": "Task enabled"}


def test_enable_disable_task_not_found(client: TestClient) -> None:
    enable_resp = client.post("/api/scheduled-tasks/missing/enable")
    assert enable_resp.status_code == 404
    assert enable_resp.json()["detail"] == "Task not found"

    disable_resp = client.post("/api/scheduled-tasks/missing/disable")
    assert disable_resp.status_code == 404
    assert disable_resp.json()["detail"] == "Task not found"
