"""Regression tests for device state release after task cancellation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from AutoGLM_GUI.phone_agent_manager import AgentMetadata, AgentState, PhoneAgentManager
from AutoGLM_GUI.task_manager import TaskManager
from AutoGLM_GUI.task_store import TaskStatus, TaskStore


def test_cancel_running_chat_task_restores_device_to_idle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cancelling a running classic chat task must release the device lock."""

    class FakeStreamingAgent:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def stream(self, message: str):
            _ = message
            self.started.set()
            await self.cancelled.wait()
            yield {
                "type": "cancelled",
                "data": {"message": "Task cancelled by user"},
            }

        async def cancel(self) -> None:
            self.cancelled.set()

    async def scenario() -> None:
        store = TaskStore(tmp_path / "tasks.db")
        manager = TaskManager(store)
        phone_manager = PhoneAgentManager()
        agent = FakeStreamingAgent()
        device_id = "device-a"

        monkeypatch.setattr(
            PhoneAgentManager,
            "get_instance",
            staticmethod(lambda: phone_manager),
        )

        async def fake_acquire_device_async(
            requested_device_id: str, **kwargs: object
        ) -> bool:
            context = str(kwargs.get("context", "default"))
            agent_key = phone_manager._make_agent_key(requested_device_id, context)
            phone_manager._metadata[agent_key] = AgentMetadata(
                device_id=requested_device_id,
                state=AgentState.BUSY,
                model_config=MagicMock(),
                agent_config=MagicMock(),
            )
            return True

        monkeypatch.setattr(
            phone_manager,
            "acquire_device_async",
            fake_acquire_device_async,
        )
        monkeypatch.setattr(
            phone_manager,
            "get_agent_with_context",
            lambda requested_device_id, **kwargs: agent,
        )

        await manager.start()

        session = await manager.create_chat_session(
            device_id=device_id,
            device_serial="serial-a",
            mode="classic",
        )
        task = await manager.submit_chat_task(
            session_id=str(session["id"]),
            device_id=device_id,
            device_serial="serial-a",
            message="cancel me",
        )
        await asyncio.wait_for(agent.started.wait(), timeout=2)

        context = f"chat:{session['id']}"
        metadata = phone_manager.get_metadata_for_device(device_id)
        assert metadata is not None
        assert metadata.state == AgentState.BUSY

        current = await manager.cancel_task(str(task["id"]))
        assert current is not None

        final_task = await manager.wait_for_task(str(task["id"]), timeout=5)
        assert final_task is not None
        assert final_task["status"] in {
            TaskStatus.CANCELLED.value,
            TaskStatus.INTERRUPTED.value,
        }

        released = phone_manager._metadata[
            phone_manager._make_agent_key(device_id, context)
        ]
        assert released.state == AgentState.IDLE
        assert released.abort_handler is None

        await manager.shutdown()
        store.close()

    asyncio.run(scenario())
