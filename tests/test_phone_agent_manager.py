"""Unit tests for PhoneAgentManager lock lifecycle."""

from __future__ import annotations

from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager


class _FakeAgent:
    def reset(self) -> None:
        pass


def test_destroy_agent_releases_stale_device_lock() -> None:
    """destroy_agent should not leave device lock in locked state."""
    manager = PhoneAgentManager()
    device_id = "test-device-1"

    manager._agents[device_id] = _FakeAgent()  # type: ignore[assignment]

    lock = manager._get_device_lock(device_id)
    assert lock.acquire(blocking=False) is True

    manager.destroy_agent(device_id)

    # Must be acquirable again; otherwise future calls will report "device busy".
    assert lock.acquire(blocking=False) is True
    lock.release()
