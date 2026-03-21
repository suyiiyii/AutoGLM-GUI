"""Unit tests for scheduler task execution semantics."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import AutoGLM_GUI.device_manager as device_manager_module
import AutoGLM_GUI.task_manager as task_manager_module
import AutoGLM_GUI.task_store as task_store_module
import AutoGLM_GUI.workflow_manager as workflow_manager_module
from AutoGLM_GUI.models.scheduled_task import ScheduledTask
from AutoGLM_GUI.scheduler_manager import SchedulerManager
from AutoGLM_GUI.task_store import TaskStatus, TaskStore


def test_scheduler_execution_counts_offline_devices_in_latest_summary(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeWorkflowManager:
        @staticmethod
        def get_workflow(workflow_uuid: str) -> dict[str, str] | None:
            if workflow_uuid != "wf-1":
                return None
            return {"uuid": "wf-1", "name": "Morning", "text": "执行签到"}

    class FakeDeviceManager:
        @staticmethod
        def get_devices() -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    serial="online-1",
                    primary_device_id="device-online-1",
                    state=SimpleNamespace(value="online"),
                )
            ]

    class FakeTaskManager:
        def __init__(self, store: TaskStore) -> None:
            self.store = store

        async def enqueue_scheduled_task(
            self,
            *,
            scheduled_task_id: str,
            workflow_uuid: str,
            device_id: str,
            device_serial: str,
            input_text: str,
            schedule_fire_id: str,
        ) -> dict[str, object]:
            task = self.store.create_task_run(
                source="scheduled",
                executor_key="scheduled_workflow",
                scheduled_task_id=scheduled_task_id,
                workflow_uuid=workflow_uuid,
                schedule_fire_id=schedule_fire_id,
                device_id=device_id,
                device_serial=device_serial,
                input_text=input_text,
            )
            self.store.update_task_terminal(
                task_id=task["id"],
                status=TaskStatus.SUCCEEDED.value,
                final_message="完成",
                error_message=None,
                step_count=1,
            )
            return task

    store = TaskStore(tmp_path / "tasks.db")
    fake_task_manager = FakeTaskManager(store)

    SchedulerManager._instance = None
    manager = SchedulerManager()
    manager._tasks = {
        "scheduled-1": ScheduledTask(
            id="scheduled-1",
            name="Morning",
            workflow_uuid="wf-1",
            device_serialnos=["online-1", "offline-1"],
            cron_expression="0 8 * * *",
            enabled=True,
        )
    }

    monkeypatch.setattr(
        workflow_manager_module, "workflow_manager", FakeWorkflowManager()
    )
    monkeypatch.setattr(
        device_manager_module.DeviceManager,
        "get_instance",
        classmethod(lambda cls: FakeDeviceManager()),
    )
    monkeypatch.setattr(task_manager_module, "task_manager", fake_task_manager)
    monkeypatch.setattr(task_store_module, "task_store", store)

    try:
        asyncio.run(manager._execute_task("scheduled-1"))

        summary = store.get_latest_schedule_summary("scheduled-1")
        tasks, total = store.list_tasks(
            source="scheduled", limit=10, offset=0, device_serial=None
        )
    finally:
        store.close()
        SchedulerManager._instance = None

    assert total == 2
    assert summary is not None
    assert summary["last_run_status"] == "partial"
    assert summary["last_run_success_count"] == 1
    assert summary["last_run_total_count"] == 2
    assert {task["device_serial"] for task in tasks} == {"online-1", "offline-1"}
    offline_task = next(task for task in tasks if task["device_serial"] == "offline-1")
    assert offline_task["status"] == TaskStatus.FAILED.value
    assert offline_task["error_message"] == "Device offline"
