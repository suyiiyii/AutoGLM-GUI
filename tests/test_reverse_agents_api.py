"""Contract tests for reverse Android Agent server foundation APIs."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.reverse_agents as reverse_agents_api
from AutoGLM_GUI.reverse_agent_protocol import (
    ReverseAgentCommand,
    ReverseAgentCommandResult,
)
from AutoGLM_GUI.reverse_agent_registry import ReverseAgentRegistry

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeClock:
    def __init__(self, start: float = 1700000000.0) -> None:
        self.current = start

    def time(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


@pytest.fixture
def reverse_agents_env(monkeypatch: pytest.MonkeyPatch) -> dict:
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
    client = TestClient(app)
    return {
        "client": client,
        "registry": registry,
        "clock": clock,
        "monkeypatch": monkeypatch,
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


def test_pairing_claim_registers_agent(reverse_agents_env: dict) -> None:
    client = reverse_agents_env["client"]
    pairing = _create_pairing(client)
    claim = _claim_pairing(client, pairing["pairing_code"])

    assert claim["pairing_id"] == pairing["pairing_id"]
    assert claim["agent_id"].startswith("reverse_agent_")
    assert claim["agent_token"]
    assert (
        claim["websocket_path"] == f"/api/reverse_agents/agents/{claim['agent_id']}/ws"
    )

    registry_response = client.get("/api/reverse_agents/registry")
    assert registry_response.status_code == 200
    agents = registry_response.json()["agents"]
    assert len(agents) == 1
    assert agents[0]["agent_id"] == claim["agent_id"]
    assert agents[0]["display_name"] == "Pixel 9 QA"
    assert agents[0]["connection_status"] == "paired"
    assert agents[0]["metadata"]["model"] == "Pixel 9"


def test_claim_pairing_rejects_unknown_code(reverse_agents_env: dict) -> None:
    response = reverse_agents_env["client"].post(
        "/api/reverse_agents/pairings/claim",
        json={"pairing_code": "BAD999"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "pairing_code_not_found"}


def test_websocket_heartbeat_updates_registry(reverse_agents_env: dict) -> None:
    client = reverse_agents_env["client"]
    clock: FakeClock = reverse_agents_env["clock"]
    pairing = _create_pairing(client)
    claim = _claim_pairing(client, pairing["pairing_code"])

    with client.websocket_connect(
        f"/api/reverse_agents/agents/{claim['agent_id']}/ws?token={claim['agent_token']}"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready == {
            "type": "session_ready",
            "agent_id": claim["agent_id"],
            "heartbeat_interval_seconds": 10,
        }

        clock.advance(5)
        websocket.send_json(
            {
                "type": "heartbeat",
                "capabilities": ["screenshot", "tap", "swipe"],
                "metadata": {"model": "Pixel 9 Pro", "battery": 88},
                "app_version": "0.3.1",
                "display_name": "Studio Pixel 9",
            }
        )
        ack = websocket.receive_json()
        assert ack == {
            "type": "heartbeat_ack",
            "agent_id": claim["agent_id"],
            "server_time": clock.time(),
            "connection_status": "connected",
        }

        registry_snapshot = client.get(
            f"/api/reverse_agents/registry/{claim['agent_id']}"
        )
        assert registry_snapshot.status_code == 200
        body = registry_snapshot.json()
        assert body["connection_status"] == "connected"
        assert body["display_name"] == "Studio Pixel 9"
        assert body["app_version"] == "0.3.1"
        assert body["capabilities"] == ["screenshot", "swipe", "tap"]
        assert body["metadata"]["battery"] == 88
        assert body["metadata"]["model"] == "Pixel 9 Pro"

    disconnected = client.get(f"/api/reverse_agents/registry/{claim['agent_id']}")
    assert disconnected.status_code == 200
    assert disconnected.json()["connection_status"] == "offline"


def test_command_endpoint_round_trip(reverse_agents_env: dict) -> None:
    client = reverse_agents_env["client"]
    registry: ReverseAgentRegistry = reverse_agents_env["registry"]
    pairing = _create_pairing(client)
    claim = _claim_pairing(client, pairing["pairing_code"])
    agent_id = claim["agent_id"]

    captured: dict[str, Any] = {}

    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def send_json(self, data: dict[str, Any]) -> None:
            self.sent.append(data)
            captured["last_sent"] = data

    fake_ws = FakeWebSocket()
    registry.register_session(agent_id=agent_id, websocket=fake_ws)

    command = ReverseAgentCommand.new(command_type="current_app", payload={})

    async def run_command() -> ReverseAgentCommandResult:
        return await registry.send_command(
            agent_id=agent_id, command=command, timeout_seconds=5
        )

    async def respond() -> None:
        # Wait until the command has been sent, then respond.
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
        return await asyncio.wait_for(
            asyncio.gather(run_command(), respond()), timeout=5
        )

    result = asyncio.run(main())[0]
    assert result.success is True
    assert result.payload["app_name"] == "com.example.app"
    assert result.command_id == command.command_id

    # REST endpoint smoke test with mocked send_command
    async def mock_send(
        *,
        agent_id: str,
        command: ReverseAgentCommand,
        timeout_seconds: float | None = None,
    ) -> ReverseAgentCommandResult:
        return ReverseAgentCommandResult.success_result(
            command_id=command.command_id,
            payload={"app_name": "com.example.app"},
        )

    monkeypatch = reverse_agents_env.get("monkeypatch")
    assert monkeypatch is not None
    monkeypatch.setattr(registry, "send_command", mock_send)

    response = client.post(
        f"/api/reverse_agents/agents/{agent_id}/commands",
        json={"command_type": "current_app", "payload": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["payload"]["app_name"] == "com.example.app"

    monkeypatch.undo()
    registry.unregister_session(agent_id=agent_id)


def test_command_endpoint_rejects_unknown_agent(reverse_agents_env: dict) -> None:
    client = reverse_agents_env["client"]
    response = client.post(
        "/api/reverse_agents/agents/reverse_agent_unknown/commands",
        json={"command_type": "screenshot"},
    )
    assert response.status_code == 404


def test_command_endpoint_rejects_offline_agent(reverse_agents_env: dict) -> None:
    client = reverse_agents_env["client"]
    pairing = _create_pairing(client)
    claim = _claim_pairing(client, pairing["pairing_code"])

    response = client.post(
        f"/api/reverse_agents/agents/{claim['agent_id']}/commands",
        json={"command_type": "screenshot"},
    )
    assert response.status_code == 503
    assert "reverse_agent_not_connected" in response.json()["detail"]


def test_registry_marks_stale_after_heartbeat_timeout(reverse_agents_env: dict) -> None:
    client = reverse_agents_env["client"]
    clock: FakeClock = reverse_agents_env["clock"]
    pairing = _create_pairing(client)
    claim = _claim_pairing(client, pairing["pairing_code"])

    with client.websocket_connect(
        f"/api/reverse_agents/agents/{claim['agent_id']}/ws?token={claim['agent_token']}"
    ) as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "heartbeat"})
        websocket.receive_json()
        clock.advance(31)

        stale_snapshot = client.get(f"/api/reverse_agents/registry/{claim['agent_id']}")
        assert stale_snapshot.status_code == 200
        assert stale_snapshot.json()["connection_status"] == "stale"
