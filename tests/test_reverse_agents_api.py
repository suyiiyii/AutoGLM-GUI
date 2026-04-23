"""Contract tests for reverse Android Agent server foundation APIs."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.reverse_agents as reverse_agents_api
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
    assert disconnected.json()["connection_status"] == "paired"


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
