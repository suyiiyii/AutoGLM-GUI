"""Unit tests for PhoneAgentManager concurrency helpers."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.phone_agent_manager import AgentMetadata, AgentState, PhoneAgentManager


pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class _DummyAgent:
    pass


def _make_idle_metadata(agent_key: str) -> AgentMetadata:
    return AgentMetadata(
        device_id=agent_key,
        state=AgentState.IDLE,
        model_config=ModelConfig(base_url="http://localhost", model_name="test"),
        agent_config=AgentConfig(device_id=agent_key),
    )


def test_acquire_device_async_auto_initializes_non_default_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PhoneAgentManager()

    async def fake_auto_init(
        self: PhoneAgentManager,
        agent_key: str,
        actual_device_id: str,
        agent_type: str | None = None,
    ) -> None:
        self._agents[agent_key] = _DummyAgent()
        self._metadata[agent_key] = _make_idle_metadata(agent_key)

    monkeypatch.setattr(
        PhoneAgentManager, "_auto_initialize_agent_unsafe", fake_auto_init
    )

    async def run_test() -> bool:
        return await manager.acquire_device_async(
            "device-1", auto_initialize=True, context="chat"
        )

    acquired = asyncio.run(run_test())
    assert acquired is True
    assert manager._metadata["device-1:chat"].state == AgentState.BUSY


def test_acquire_device_async_raises_when_metadata_missing_after_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PhoneAgentManager()

    async def fake_auto_init(
        self: PhoneAgentManager,
        agent_key: str,
        actual_device_id: str,
        agent_type: str | None = None,
    ) -> None:
        # Simulate a concurrent destroy: the agent exists but metadata was removed.
        self._agents[agent_key] = _DummyAgent()

    monkeypatch.setattr(
        PhoneAgentManager, "_auto_initialize_agent_unsafe", fake_auto_init
    )

    async def run_test() -> None:
        with pytest.raises(Exception):  # noqa: B017
            await manager.acquire_device_async(
                "device-1", auto_initialize=True, context="chat"
            )

    asyncio.run(run_test())


def test_acquire_device_async_releases_lock_after_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PhoneAgentManager()
    released = threading.Event()
    release_calls: list[tuple[str, str]] = []

    async def fake_acquire(device_id: str, **kwargs) -> bool:
        _ = (device_id, kwargs)
        await asyncio.to_thread(time.sleep, 0.05)
        return True

    async def fake_release(device_id: str, context: str = "default") -> None:
        release_calls.append((device_id, context))
        released.set()

    monkeypatch.setattr(manager, "_acquire_device_impl", fake_acquire)
    monkeypatch.setattr(manager, "release_device_async", fake_release)

    async def run_test() -> None:
        task = asyncio.create_task(
            manager.acquire_device_async(
                "device-1",
                auto_initialize=True,
                context="chat",
            )
        )

        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        cleanup_completed = await asyncio.to_thread(released.wait, 1.0)
        assert cleanup_completed is True

    asyncio.run(run_test())

    assert release_calls == [("device-1", "chat")]
