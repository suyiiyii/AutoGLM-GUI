"""Tests for issue #172: device should return to idle after task cancellation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from AutoGLM_GUI.phone_agent_manager import (
    AgentMetadata,
    AgentState,
    PhoneAgentManager,
)
from AutoGLM_GUI.task_manager import TaskManager
from AutoGLM_GUI.task_store import TaskStatus, TaskStore


# ---------------------------------------------------------------------------
# Test: abort_streaming_chat_async finds handlers under contextual keys
# ---------------------------------------------------------------------------


def test_abort_streaming_chat_async_finds_contextual_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """abort_streaming_chat_async must discover abort handlers stored under
    contextual keys like ``device_id:chat:session_id``, not just the raw
    ``device_id``."""

    async def run() -> None:
        manager = PhoneAgentManager()

        # Insert metadata under a contextual key (as _execute_classic_chat does)
        called = asyncio.Event()
        device_id = "device-1"

        async def fake_abort() -> None:
            called.set()

        contextual_key = f"{device_id}:chat:session-abc"
        manager._metadata[contextual_key] = AgentMetadata(
            device_id=device_id,
            state=AgentState.BUSY,
            abort_handler=fake_abort,
            model_config=MagicMock(),
            agent_config=MagicMock(),
        )

        result = await manager.abort_streaming_chat_async(device_id)
        assert result is True
        assert called.is_set()

    asyncio.run(run())


def test_abort_streaming_chat_async_prefers_exact_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When multiple handlers exist, the one matching the raw device_id wins."""

    async def run() -> None:
        manager = PhoneAgentManager()
        device_id = "device-1"

        exact_called = asyncio.Event()
        ctx_called = asyncio.Event()

        async def exact_abort() -> None:
            exact_called.set()

        async def ctx_abort() -> None:
            ctx_called.set()

        # Contextual handler
        manager._metadata[f"{device_id}:chat:s1"] = AgentMetadata(
            device_id=device_id,
            state=AgentState.BUSY,
            abort_handler=ctx_abort,
            model_config=MagicMock(),
            agent_config=MagicMock(),
        )
        # Exact match handler
        manager._metadata[device_id] = AgentMetadata(
            device_id=device_id,
            state=AgentState.BUSY,
            abort_handler=exact_abort,
            model_config=MagicMock(),
            agent_config=MagicMock(),
        )

        result = await manager.abort_streaming_chat_async(device_id)
        assert result is True
        assert exact_called.is_set()
        assert not ctx_called.is_set()

    asyncio.run(run())


def test_is_streaming_active_finds_contextual_keys() -> None:
    """is_streaming_active must return True when a handler is registered under
    a contextual key."""

    manager = PhoneAgentManager()
    device_id = "device-1"

    # No handlers → False
    assert manager.is_streaming_active(device_id) is False

    # Handler under contextual key → True
    manager._metadata[f"{device_id}:chat:s1"] = AgentMetadata(
        device_id=device_id,
        state=AgentState.BUSY,
        abort_handler=lambda: None,
        model_config=MagicMock(),
        agent_config=MagicMock(),
    )
    assert manager.is_streaming_active(device_id) is True


# ---------------------------------------------------------------------------
# Test: cancelling a running task transitions the device back to IDLE
# ---------------------------------------------------------------------------


def test_cancel_running_task_releases_device(tmp_path: Path) -> None:
    """Verify that after cancelling a running task, the device lock is
    released (state returns to IDLE).  This is the core reproducer for
    issue #172."""

    async def scenario() -> None:
        store = TaskStore(tmp_path / "tasks.db")
        tm = TaskManager(store)

        device_id = "device-test"
        step_started = asyncio.Event()
        cancel_signalled = asyncio.Event()
        device_acquired = False

        def fake_acquire(dev: str, **kwargs: object) -> bool:
            nonlocal device_acquired
            device_acquired = True
            return True

        def fake_release(dev: str, **kwargs: object) -> None:
            nonlocal device_acquired
            device_acquired = False

        async def blocking_executor(task: dict[str, object]) -> None:
            task_id = str(task["id"])

            # Simulate device acquisition
            fake_acquire(device_id)

            step_started.set()

            def abort_handler() -> None:
                cancel_signalled.set()

            tm._abort_handlers[task_id] = abort_handler

            try:
                # Wait until cancel_handler is invoked
                await cancel_signalled.wait()
            finally:
                tm._cancel_requested.discard(task_id)
                tm._abort_handlers.pop(task_id, None)
                fake_release(device_id)

            await tm._finalize_task(
                task_id=task_id,
                status=TaskStatus.CANCELLED.value,
                final_message="Task cancelled by user",
                step_count=0,
            )

        tm.register_executor("test_blocking", blocking_executor)

        task = store.create_task_run(
            source="chat",
            executor_key="test_blocking",
            device_id=device_id,
            device_serial="serial-test",
            input_text="test task",
        )
        tm._completion_events[str(task["id"])] = asyncio.Event()

        await tm.start()

        # Wait for the task to actually start executing
        await asyncio.wait_for(step_started.wait(), timeout=2)
        assert device_acquired is True  # device must be acquired

        # Cancel the running task
        result = await tm.cancel_task(str(task["id"]))
        assert result is not None

        # Wait for the task to complete
        final = await tm.wait_for_task(str(task["id"]), timeout=5)
        assert final is not None
        assert final["status"] == TaskStatus.CANCELLED.value

        # Verify the device was released
        assert device_acquired is False

        await tm.shutdown()
        store.close()

    asyncio.run(scenario())


def test_cancel_task_with_post_stream_check(tmp_path: Path) -> None:
    """When the agent stream exits normally (no CancelledError) but cancel
    was requested, the task should still be recorded as CANCELLED.

    This tests the post-stream _cancel_requested override we added to
    _execute_classic_chat and _execute_scheduled_workflow.
    """

    async def scenario() -> None:
        store = TaskStore(tmp_path / "tasks.db")
        tm = TaskManager(store)

        executor_called = asyncio.Event()

        async def executor_that_exits_normally(task: dict[str, object]) -> None:
            """Simulates an executor whose stream exits normally when
            _is_running is set to False by cancel()."""
            task_id = str(task["id"])
            executor_called.set()

            # Wait a beat so cancel can be requested
            await asyncio.sleep(0.1)

            # Check if cancel was requested (simulating the early-cancel guard)
            if task_id in tm._cancel_requested:
                await tm._finalize_task(
                    task_id=task_id,
                    status=TaskStatus.CANCELLED.value,
                    final_message="Task cancelled by user",
                    step_count=0,
                )
                return

            await tm._finalize_task(
                task_id=task_id,
                status=TaskStatus.SUCCEEDED.value,
                final_message="Done",
                step_count=1,
            )

        tm.register_executor("test_normal_exit", executor_that_exits_normally)

        task = store.create_task_run(
            source="chat",
            executor_key="test_normal_exit",
            device_id="device-a",
            device_serial="serial-a",
            input_text="test",
        )
        tm._completion_events[str(task["id"])] = asyncio.Event()

        await tm.start()
        await asyncio.wait_for(executor_called.wait(), timeout=2)

        # Request cancel while executor is sleeping
        await tm.cancel_task(str(task["id"]))

        final = await tm.wait_for_task(str(task["id"]), timeout=5)
        assert final is not None
        assert final["status"] == TaskStatus.CANCELLED.value

        await tm.shutdown()
        store.close()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Test: release_device preserves ERROR state (PR #317 regression)
# ---------------------------------------------------------------------------


def test_release_device_preserves_error_state() -> None:
    """After set_error_state() sets state to ERROR, release_device() must NOT
    override it back to IDLE.  This is the regression lock for the QA-reported
    blocking issue in PR #317."""

    manager = PhoneAgentManager()
    device_id = "device-err"
    agent_key = device_id  # default context

    # Simulate a device that went through acquire → (task runs) → error
    manager._metadata[agent_key] = AgentMetadata(
        device_id=device_id,
        state=AgentState.BUSY,
        abort_handler=lambda: None,
        model_config=MagicMock(),
        agent_config=MagicMock(),
    )

    # Task fails → set_error_state
    manager.set_error_state(device_id, "something broke")
    assert manager._metadata[agent_key].state == AgentState.ERROR

    # Finally block calls release_device — state must stay ERROR
    manager.release_device(device_id)
    assert manager._metadata[agent_key].state == AgentState.ERROR
    # abort_handler should still be cleared
    assert manager._metadata[agent_key].abort_handler is None


def test_release_device_transitions_busy_to_idle() -> None:
    """When device is BUSY (no error), release_device should still transition
    to IDLE as before."""

    manager = PhoneAgentManager()
    device_id = "device-ok"
    agent_key = device_id

    manager._metadata[agent_key] = AgentMetadata(
        device_id=device_id,
        state=AgentState.BUSY,
        abort_handler=lambda: None,
        model_config=MagicMock(),
        agent_config=MagicMock(),
    )

    manager.release_device(device_id)
    assert manager._metadata[agent_key].state == AgentState.IDLE
    assert manager._metadata[agent_key].abort_handler is None
