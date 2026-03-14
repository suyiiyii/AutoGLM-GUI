"""Unit tests for PhoneAgentManager concurrency helpers."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager


pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


def test_acquire_device_async_releases_lock_after_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PhoneAgentManager()
    released = threading.Event()
    release_calls: list[tuple[str, str]] = []

    def fake_acquire(device_id: str, **kwargs) -> bool:
        _ = (device_id, kwargs)
        time.sleep(0.05)
        return True

    def fake_release(device_id: str, context: str = "default") -> None:
        release_calls.append((device_id, context))
        released.set()

    monkeypatch.setattr(manager, "acquire_device", fake_acquire)
    monkeypatch.setattr(manager, "release_device", fake_release)

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
