"""Contract tests for agent lifecycle/status API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.phone_agent_manager as phone_agent_manager_module
from AutoGLM_GUI.api.agents import router as agents_router
from AutoGLM_GUI.exceptions import AgentNotInitializedError
from AutoGLM_GUI.version import APP_VERSION

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeAgent:
    def __init__(self, step_count: int = 0) -> None:
        self.step_count = step_count


class FakePhoneAgentManager:
    def __init__(self) -> None:
        self.agents: dict[str, FakeAgent] = {}
        self.reset_calls: list[str] = []
        self.abort_results: dict[str, bool] = {}

    def list_agents(self) -> list[str]:
        return list(self.agents.keys())

    def is_initialized(self, device_id: str) -> bool:
        return device_id in self.agents

    def get_agent(self, device_id: str) -> FakeAgent:
        return self.agents[device_id]

    def reset_agent(self, device_id: str) -> None:
        if device_id not in self.agents:
            raise AgentNotInitializedError(device_id)
        self.reset_calls.append(device_id)
        self.agents[device_id].step_count = 0

    async def abort_streaming_chat_async(self, device_id: str) -> bool:
        return self.abort_results.get(device_id, False)


@pytest.fixture
def fake_manager() -> FakePhoneAgentManager:
    return FakePhoneAgentManager()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, fake_manager: FakePhoneAgentManager
) -> TestClient:
    monkeypatch.setattr(
        phone_agent_manager_module.PhoneAgentManager,
        "get_instance",
        staticmethod(lambda: fake_manager),
    )

    app = FastAPI()
    app.include_router(agents_router)
    return TestClient(app)


def test_status_without_device_reports_global_initialization(
    client: TestClient, fake_manager: FakePhoneAgentManager
) -> None:
    fake_manager.agents["dev-1"] = FakeAgent(step_count=3)

    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "version": APP_VERSION,
        "initialized": True,
        "step_count": 0,
    }


def test_status_with_unknown_device_returns_uninitialized(client: TestClient) -> None:
    response = client.get("/api/status", params={"device_id": "missing-device"})

    assert response.status_code == 200
    assert response.json() == {
        "version": APP_VERSION,
        "initialized": False,
        "step_count": 0,
    }


def test_status_with_initialized_device_returns_step_count(
    client: TestClient, fake_manager: FakePhoneAgentManager
) -> None:
    fake_manager.agents["dev-2"] = FakeAgent(step_count=7)

    response = client.get("/api/status", params={"device_id": "dev-2"})

    assert response.status_code == 200
    assert response.json() == {
        "version": APP_VERSION,
        "initialized": True,
        "step_count": 7,
    }


def test_reset_agent_success(
    client: TestClient, fake_manager: FakePhoneAgentManager
) -> None:
    fake_manager.agents["dev-3"] = FakeAgent(step_count=5)

    response = client.post("/api/reset", json={"device_id": "dev-3"})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "device_id": "dev-3",
        "message": "Agent reset for device dev-3",
    }
    assert fake_manager.reset_calls == ["dev-3"]
    assert fake_manager.agents["dev-3"].step_count == 0


def test_reset_agent_not_found_returns_404(client: TestClient) -> None:
    response = client.post("/api/reset", json={"device_id": "missing-device"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Device missing-device not found"


def test_abort_chat_success(
    client: TestClient, fake_manager: FakePhoneAgentManager
) -> None:
    fake_manager.abort_results["dev-4"] = True

    response = client.post("/api/chat/abort", json={"device_id": "dev-4"})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Abort requested",
    }


def test_abort_chat_without_active_stream_returns_success_false(
    client: TestClient,
) -> None:
    response = client.post("/api/chat/abort", json={"device_id": "idle-device"})

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "No active chat found",
    }
