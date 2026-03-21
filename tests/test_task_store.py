"""Tests for task store persistence and aggregation."""

from __future__ import annotations

from pathlib import Path

from AutoGLM_GUI.task_store import TaskStatus, TaskStore


def test_task_store_creates_sessions_and_task_events(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    session = store.create_session(
        kind="chat",
        mode="classic",
        device_id="device-1",
        device_serial="serial-1",
    )
    task = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        session_id=session["id"],
        device_id="device-1",
        device_serial="serial-1",
        input_text="打开微信",
    )
    store.append_event(
        task_id=task["id"],
        event_type="thinking",
        payload={"chunk": "先看屏幕"},
    )

    tasks, total = store.list_session_tasks(session["id"])
    events = store.list_task_events(task["id"])

    assert total == 1
    assert tasks[0]["input_text"] == "打开微信"
    assert events[0]["event_type"] == "status"
    assert events[1]["payload"] == {"chunk": "先看屏幕"}


def test_task_store_can_cancel_queued_tasks_and_interrupt_running(
    tmp_path: Path,
) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    queued = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-1",
        device_serial="serial-1",
        input_text="任务一",
    )
    cancelled = store.cancel_queued_task(queued["id"])
    running = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-1",
        device_serial="serial-1",
        input_text="任务二",
        status=TaskStatus.RUNNING.value,
    )
    interrupted_count = store.mark_running_tasks_interrupted()

    assert cancelled is not None
    assert cancelled["status"] == TaskStatus.CANCELLED.value
    assert interrupted_count == 1
    assert store.get_task(running["id"])["status"] == TaskStatus.INTERRUPTED.value


def test_task_store_aggregates_latest_schedule_batch(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    first = store.create_task_run(
        source="scheduled",
        executor_key="scheduled_workflow",
        scheduled_task_id="scheduled-1",
        workflow_uuid="wf-1",
        schedule_fire_id="fire-1",
        device_id="device-1",
        device_serial="serial-1",
        input_text="签到",
    )
    second = store.create_task_run(
        source="scheduled",
        executor_key="scheduled_workflow",
        scheduled_task_id="scheduled-1",
        workflow_uuid="wf-1",
        schedule_fire_id="fire-1",
        device_id="device-2",
        device_serial="serial-2",
        input_text="签到",
    )
    store.update_task_terminal(
        task_id=first["id"],
        status=TaskStatus.SUCCEEDED.value,
        final_message="完成",
        error_message=None,
        step_count=2,
    )
    store.update_task_terminal(
        task_id=second["id"],
        status=TaskStatus.FAILED.value,
        final_message="失败",
        error_message="失败",
        step_count=1,
    )

    summary = store.get_latest_schedule_summary("scheduled-1")

    assert summary is not None
    assert summary["last_run_status"] == "partial"
    assert summary["last_run_success_count"] == 1
    assert summary["last_run_total_count"] == 2


def test_clear_device_history_keeps_active_tasks(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")

    queued = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-1",
        device_serial="serial-1",
        input_text="排队中",
    )
    running = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-1",
        device_serial="serial-1",
        input_text="执行中",
        status=TaskStatus.RUNNING.value,
    )
    finished = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-1",
        device_serial="serial-1",
        input_text="已完成",
    )
    store.update_task_terminal(
        task_id=finished["id"],
        status=TaskStatus.SUCCEEDED.value,
        final_message="完成",
        error_message=None,
        step_count=1,
    )

    deleted_count = store.clear_device_history("serial-1")

    assert deleted_count == 1
    assert store.get_task(queued["id"]) is not None
    assert store.get_task(running["id"]) is not None
    assert store.get_task(finished["id"]) is None
