"""Contract tests for reverse agent integration with DeviceManager."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.devices as devices_api
import AutoGLM_GUI.api.reverse_agents as reverse_agents_api
from AutoGLM_GUI.device_manager import DeviceManager
from AutoGLM_GUI.reverse_agent_protocol import (
    ReverseAgentCommand,
    ReverseAgentCommandResult,
)
from AutoGLM_GUI.reverse_agent_registry import ReverseAgentRegistry

pytestmark = [pytest.mark.contract]


class FakeClock:
    def __init__(self, start: float = 1700000000.0) -> None:
        self.current = start

    def time(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset DeviceManager singleton to avoid cross-test state leakage."""
    DeviceManager._instance = None
    yield
    DeviceManager._instance = None


@pytest.fixture
def reverse_agent_env(monkeypatch: pytest.MonkeyPatch) -> dict:
    clock = FakeClock()
    registry = ReverseAgentRegistry(
        pairing_ttl_seconds=120,
        heartbeat_timeout_seconds=30,
        time_fn=clock.time,
    )
    monkeypatch.setattr(
        reverse_agents_api,
        "get_reverse_agent_registry",
        lambda: registry,
    )

    app = FastAPI()
    app.include_router(reverse_agents_api.router)
    app.include_router(devices_api.router)
    client = TestClient(app)
    return {
        "client": client,
        "registry": registry,
        "clock": clock,
    }


def _create_pairing(client: TestClient) -> dict:
    response = client.post(
        "/api/reverse_agents/pairings",
        json={"display_name": "QA Android Agent"},
    )
    assert response.status_code == 200
    return response.json()


def _claim_pairing(client: TestClient, pairing_code: str) -> dict:
    response = client.post(
        "/api/reverse_agents/pairings/claim",
        json={
            "pairing_code": pairing_code,
            "display_name": "Pixel 9 QA",
            "app_version": "0.3.0",
            "platform": "android",
            "capabilities": ["screenshot", "tap"],
            "metadata": {"model": "Pixel 9"},
        },
    )
    assert response.status_code == 200
    return response.json()


def test_reverse_agent_appears_in_device_list(reverse_agent_env: dict) -> None:
    client = reverse_agent_env["client"]
    pairing = _create_pairing(client)
    claim = _claim_pairing(client, pairing["pairing_code"])
    agent_id = claim["agent_id"]

    with client.websocket_connect(
        f"/api/reverse_agents/agents/{agent_id}/ws?token={claim['agent_token']}"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "session_ready"

        device_response = client.get("/api/devices")
        assert device_response.status_code == 200
        devices = device_response.json()["devices"]
        reverse_devices = [d for d in devices if d["serial"] == f"reverse:{agent_id}"]
        assert len(reverse_devices) == 1
        device = reverse_devices[0]
        assert device["connection_type"] == "reverse_agent"
        assert device["model"] == "Pixel 9"
        assert device["status"] == "device"


def test_reverse_agent_command_via_device_manager(reverse_agent_env: dict) -> None:
    client = reverse_agent_env["client"]
    registry: ReverseAgentRegistry = reverse_agent_env["registry"]
    pairing = _create_pairing(client)
    claim = _claim_pairing(client, pairing["pairing_code"])
    agent_id = claim["agent_id"]

    captured: dict = {}

    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict] = []

        async def send_json(self, data: dict) -> None:
            self.sent.append(data)
            captured["last_sent"] = data

    fake_ws = FakeWebSocket()

    with client.websocket_connect(
        f"/api/reverse_agents/agents/{agent_id}/ws?token={claim['agent_token']}"
    ) as websocket:
        websocket.receive_json()  # session_ready

        # Replace the real websocket with our fake one for deterministic testing.
        registry.unregister_session(agent_id=agent_id)
        registry.register_session(agent_id=agent_id, websocket=fake_ws)

        device_manager = DeviceManager.get_instance()
        device_manager.register_reverse_agent(agent_id=agent_id)
        device = device_manager.get_device_protocol(agent_id)
        assert device.device_id == agent_id

        command = ReverseAgentCommand.new(command_type="current_app", payload={})

        async def run_command() -> ReverseAgentCommandResult:
            return await registry.send_command(
                agent_id=agent_id, command=command, timeout_seconds=5
            )

        async def respond() -> None:
            for _ in range(50):
                await asyncio.sleep(0.01)
                if "last_sent" in captured:
                    break
            sent = captured["last_sent"]
            registry.handle_command_result(
                agent_id=agent_id,
                result=ReverseAgentCommandResult.success_result(
                    command_id=sent["command_id"],
                    payload={"app_name": "com.example.app"},
                ),
            )

        async def main() -> ReverseAgentCommandResult:
            return (await asyncio.gather(run_command(), respond()))[0]

        result = asyncio.run(asyncio.wait_for(main(), timeout=5))
        assert result.success is True
        assert result.payload["app_name"] == "com.example.app"
