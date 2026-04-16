"""Unit tests for task manager queueing and cancellation semantics."""

from __future__ import annotations

import asyncio
from pathlib import Path

from AutoGLM_GUI.task_manager import TaskManager
from AutoGLM_GUI.task_store import TaskStatus, TaskStore


def test_task_manager_runs_fifo_per_device_and_parallel_across_devices(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = TaskStore(tmp_path / "tasks.db")
        manager = TaskManager(store)
        start_order: list[str] = []
        active_count = 0
        max_active = 0
        lock = asyncio.Lock()

        async def fake_executor(task: dict[str, object]) -> None:
            nonlocal active_count, max_active
            async with lock:
                start_order.append(str(task["id"]))
                active_count += 1
                max_active = max(max_active, active_count)
            await asyncio.sleep(0.05)
            await manager._finalize_task(
                task_id=str(task["id"]),
                status=TaskStatus.SUCCEEDED.value,
                final_message=str(task["input_text"]),
                step_count=1,
            )
            async with lock:
                active_count -= 1

        manager.register_executor("fake", fake_executor)

        task_a = store.create_task_run(
            source="chat",
            executor_key="fake",
            device_id="device-a",
            device_serial="serial-a",
            input_text="A1",
        )
        task_b = store.create_task_run(
            source="chat",
            executor_key="fake",
            device_id="device-a",
            device_serial="serial-a",
            input_text="A2",
        )
        task_c = store.create_task_run(
            source="chat",
            executor_key="fake",
            device_id="device-b",
            device_serial="serial-b",
            input_text="B1",
        )

        for task in (task_a, task_b, task_c):
            manager._completion_events[str(task["id"])] = asyncio.Event()

        await manager.start()
        await asyncio.gather(
            manager.wait_for_task(str(task_a["id"]), timeout=2),
            manager.wait_for_task(str(task_b["id"]), timeout=2),
            manager.wait_for_task(str(task_c["id"]), timeout=2),
        )

        assert start_order.index(str(task_a["id"])) < start_order.index(
            str(task_b["id"])
        )
        assert max_active >= 2
        assert store.get_task(str(task_a["id"]))["status"] == TaskStatus.SUCCEEDED.value
        assert store.get_task(str(task_b["id"]))["status"] == TaskStatus.SUCCEEDED.value
        assert store.get_task(str(task_c["id"]))["status"] == TaskStatus.SUCCEEDED.value

        await manager.shutdown()
        store.close()

    asyncio.run(scenario())


def test_task_manager_can_cancel_queued_task(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = TaskStore(tmp_path / "tasks.db")
        manager = TaskManager(store)
        unblock = asyncio.Event()
        started = asyncio.Event()

        async def blocking_executor(task: dict[str, object]) -> None:
            started.set()
            await unblock.wait()
            await manager._finalize_task(
                task_id=str(task["id"]),
                status=TaskStatus.SUCCEEDED.value,
                final_message="done",
                step_count=1,
            )

        manager.register_executor("fake", blocking_executor)

        running = store.create_task_run(
            source="chat",
            executor_key="fake",
            device_id="device-a",
            device_serial="serial-a",
            input_text="first",
        )
        queued = store.create_task_run(
            source="chat",
            executor_key="fake",
            device_id="device-a",
            device_serial="serial-a",
            input_text="second",
        )

        for task in (running, queued):
            manager._completion_events[str(task["id"])] = asyncio.Event()

        await manager.start()
        await asyncio.wait_for(started.wait(), timeout=2)

        cancelled = await manager.cancel_task(str(queued["id"]))
        assert cancelled is not None
        assert cancelled["status"] == TaskStatus.CANCELLED.value

        unblock.set()
        await manager.wait_for_task(str(running["id"]), timeout=2)
        final_queued = await manager.wait_for_task(str(queued["id"]), timeout=2)
        assert final_queued is not None
        assert final_queued["status"] == TaskStatus.CANCELLED.value
        assert final_queued["stop_reason"] == "user_stopped"

        await manager.shutdown()
        store.close()

    asyncio.run(scenario())


def test_task_manager_can_cancel_running_task(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = TaskStore(tmp_path / "tasks.db")
        manager = TaskManager(store)
        running = asyncio.Event()
        cancelled = asyncio.Event()

        async def cancellable_executor(task: dict[str, object]) -> None:
            task_id = str(task["id"])

            def abort_handler() -> None:
                cancelled.set()

            manager._abort_handlers[task_id] = abort_handler
            running.set()
            await cancelled.wait()
            manager._abort_handlers.pop(task_id, None)
            manager._cancel_requested.discard(task_id)
            await manager._finalize_task(
                task_id=task_id,
                status=TaskStatus.CANCELLED.value,
                final_message="Task cancelled by user",
                step_count=0,
            )

        manager.register_executor("fake", cancellable_executor)

        task = store.create_task_run(
            source="chat",
            executor_key="fake",
            device_id="device-a",
            device_serial="serial-a",
            input_text="cancel me",
        )
        manager._completion_events[str(task["id"])] = asyncio.Event()

        await manager.start()
        await asyncio.wait_for(running.wait(), timeout=2)

        current = await manager.cancel_task(str(task["id"]))
        assert current is not None

        final_task = await manager.wait_for_task(str(task["id"]), timeout=2)
        assert final_task is not None
        assert final_task["status"] == TaskStatus.CANCELLED.value
        assert final_task["stop_reason"] == "user_stopped"

        await manager.shutdown()
        store.close()

    asyncio.run(scenario())


def test_task_manager_marks_running_tasks_interrupted_on_start(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-a",
        device_serial="serial-a",
        input_text="resume me",
        status=TaskStatus.RUNNING.value,
    )
    manager = TaskManager(store)

    asyncio.run(manager.start())

    recovered = store.get_task(str(task["id"]))
    events = store.list_task_events(str(task["id"]))

    assert recovered is not None
    assert recovered["status"] == TaskStatus.INTERRUPTED.value
    assert recovered["stop_reason"] == "service_interrupted"
    assert any(event["event_type"] == "error" for event in events)

    asyncio.run(manager.shutdown())
    store.close()


def test_submit_chat_task_uses_layered_executor_for_layered_sessions(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = TaskStore(tmp_path / "tasks.db")
        manager = TaskManager(store)
        session = await manager.create_chat_session(
            device_id="device-a",
            device_serial="serial-a",
            mode="layered",
        )

        task = await manager.submit_chat_task(
            session_id=str(session["id"]),
            device_id="device-a",
            device_serial="serial-a",
            message="复杂任务",
        )

        assert task["executor_key"] == "layered_chat"
        assert task["source"] == "chat"

        await manager.shutdown()
        store.close()

    asyncio.run(scenario())
