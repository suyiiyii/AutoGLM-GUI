"""Contract tests for chat streaming and config API endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.config_manager as config_manager_module
import AutoGLM_GUI.device_manager as device_manager_module
import AutoGLM_GUI.phone_agent_manager as phone_agent_manager_module
from AutoGLM_GUI.api.agents import router as agents_router
from AutoGLM_GUI.exceptions import AgentInitializationError, DeviceBusyError

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeAsyncAgent:
    def __init__(self) -> None:
        self.step_count = 2
        self.run_result = "ok"
        self.run_error: Exception | None = None
        self.stream_events: list[dict[str, Any]] = []
        self.stream_error: Exception | None = None
        self.cancelled = False

    async def run(self, message: str) -> str:
        _ = message
        if self.run_error is not None:
            raise self.run_error
        return self.run_result

    async def stream(self, message: str):
        _ = message
        if self.stream_error is not None:
            raise self.stream_error
        for event in self.stream_events:
            yield event

    async def cancel(self) -> None:
        self.cancelled = True


class FakeSyncAgent:
    def __init__(self) -> None:
        self.step_count = 1
        self.run_result = "sync ok"
        self.run_error: Exception | None = None

    def run(self, message: str) -> str:
        _ = message
        if self.run_error is not None:
            raise self.run_error
        return self.run_result


class FakePhoneAgentManager:
    def __init__(self) -> None:
        self.acquire_mode = "ok"
        self.agent = FakeAsyncAgent()
        self.release_calls: list[str] = []
        self.registered_handlers: dict[str, Any] = {}
        self.unregistered_handlers: list[str] = []
        self.destroy_candidates: list[str] = []
        self.destroy_calls: list[str] = []

    def acquire_device(self, device_id: str, **kwargs) -> bool:
        _ = kwargs
        if self.acquire_mode == "busy":
            raise DeviceBusyError()
        if self.acquire_mode == "init_error":
            raise AgentInitializationError("missing config")
        return True

    def get_agent_with_context(self, device_id: str, **kwargs) -> Any:
        _ = (device_id, kwargs)
        return self.agent

    def release_device(self, device_id: str) -> None:
        self.release_calls.append(device_id)

    def register_abort_handler(self, device_id: str, handler: Any) -> None:
        self.registered_handlers[device_id] = handler

    def unregister_abort_handler(self, device_id: str) -> None:
        self.unregistered_handlers.append(device_id)

    def list_agents(self) -> list[str]:
        return list(self.destroy_candidates)

    def destroy_agent(self, device_id: str) -> None:
        self.destroy_calls.append(device_id)
        if device_id.endswith("-fail"):
            raise RuntimeError("destroy failed")


class FakeConfigManager:
    def __init__(self) -> None:
        self.effective_config = SimpleNamespace(
            base_url="http://localhost:8080/v1",
            model_name="autoglm-phone-9b",
            api_key="EMPTY",
            agent_type="glm-async",
            agent_config_params={"thinking_mode": "fast"},
            default_max_steps=120,
            layered_max_turns=50,
            decision_base_url="http://localhost:9999/v1",
            decision_model_name="planner-model",
            decision_api_key="secret",
        )
        self.source = SimpleNamespace(
            value="config file (~/.config/autoglm/config.json)"
        )
        self.conflicts: list[SimpleNamespace] = []
        self.save_result = True
        self.delete_result = True
        self.sync_called = False
        self.save_kwargs: dict[str, Any] | None = None

    def load_file_config(self) -> None:
        return None

    def get_effective_config(self) -> SimpleNamespace:
        return self.effective_config

    def get_config_source(self) -> SimpleNamespace:
        return self.source

    def detect_conflicts(self) -> list[SimpleNamespace]:
        return self.conflicts

    def save_file_config(self, **kwargs) -> bool:
        self.save_kwargs = kwargs
        return self.save_result

    def sync_to_env(self) -> None:
        self.sync_called = True

    def get_config_path(self) -> str:
        return "/tmp/autoglm/config.json"

    def delete_file_config(self) -> bool:
        return self.delete_result


class FakeDeviceManager:
    def get_serial_by_device_id(self, device_id: str) -> str | None:
        _ = device_id
        return None


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    fake_phone_manager = FakePhoneAgentManager()
    fake_config_manager = FakeConfigManager()

    monkeypatch.setattr(
        phone_agent_manager_module.PhoneAgentManager,
        "get_instance",
        staticmethod(lambda: fake_phone_manager),
    )
    monkeypatch.setattr(config_manager_module, "config_manager", fake_config_manager)
    monkeypatch.setattr(
        device_manager_module.DeviceManager,
        "get_instance",
        staticmethod(lambda: FakeDeviceManager()),
    )

    app = FastAPI()
    app.include_router(agents_router)

    return {
        "client": TestClient(app),
        "phone_manager": fake_phone_manager,
        "config_manager": fake_config_manager,
    }


def test_chat_success_contract(env: dict[str, Any]) -> None:
    env["phone_manager"].agent.run_result = "task finished"
    env["phone_manager"].agent.step_count = 3

    response = env["client"].post(
        "/api/chat",
        json={"device_id": "device-1", "message": "open settings"},
    )

    assert response.status_code == 200
    assert response.json() == {"result": "task finished", "steps": 3, "success": True}
    assert env["phone_manager"].release_calls == ["device-1"]


def test_chat_returns_409_when_device_busy(env: dict[str, Any]) -> None:
    env["phone_manager"].acquire_mode = "busy"

    response = env["client"].post(
        "/api/chat",
        json={"device_id": "busy-device", "message": "open settings"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Device busy-device is busy. Please wait."


def test_chat_returns_500_when_agent_initialization_fails(env: dict[str, Any]) -> None:
    env["phone_manager"].acquire_mode = "init_error"

    response = env["client"].post(
        "/api/chat",
        json={"device_id": "device-1", "message": "open settings"},
    )

    assert response.status_code == 500
    assert "初始化失败" in response.json()["detail"]


def test_chat_unexpected_error_returns_success_false(env: dict[str, Any]) -> None:
    env["phone_manager"].agent.run_error = RuntimeError("agent crashed")

    response = env["client"].post(
        "/api/chat",
        json={"device_id": "device-2", "message": "open settings"},
    )

    assert response.status_code == 200
    assert response.json() == {"result": "agent crashed", "steps": 0, "success": False}
    assert env["phone_manager"].release_calls == ["device-2"]


def test_chat_supports_sync_agent(env: dict[str, Any]) -> None:
    env["phone_manager"].agent = FakeSyncAgent()

    response = env["client"].post(
        "/api/chat",
        json={"device_id": "device-sync", "message": "open settings"},
    )

    assert response.status_code == 200
    assert response.json() == {"result": "sync ok", "steps": 1, "success": True}
    assert env["phone_manager"].release_calls == ["device-sync"]


def test_chat_stream_returns_409_when_device_busy(env: dict[str, Any]) -> None:
    env["phone_manager"].acquire_mode = "busy"

    response = env["client"].post(
        "/api/chat/stream",
        json={"device_id": "busy-device", "message": "open settings"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Device busy-device is busy. Please wait."


def test_chat_stream_returns_500_on_initialization_error(env: dict[str, Any]) -> None:
    env["phone_manager"].acquire_mode = "init_error"

    response = env["client"].post(
        "/api/chat/stream",
        json={"device_id": "device-1", "message": "open settings"},
    )

    assert response.status_code == 500
    assert "初始化失败" in response.json()["detail"]


def test_chat_stream_emits_sse_events(env: dict[str, Any]) -> None:
    env["phone_manager"].agent.stream_events = [
        {
            "type": "step",
            "data": {
                "step": 1,
                "thinking": "locating button",
                "action": {"tap": [1, 2]},
            },
        },
        {
            "type": "done",
            "data": {"message": "finished", "success": True, "steps": 1},
        },
    ]

    response = env["client"].post(
        "/api/chat/stream",
        json={"device_id": "device-3", "message": "open settings"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    assert "event: step" in body
    assert '"type": "step"' in body
    assert "event: done" in body
    assert '"message": "finished"' in body


def test_chat_stream_returns_error_for_non_async_agent(env: dict[str, Any]) -> None:
    env["phone_manager"].agent = FakeSyncAgent()

    response = env["client"].post(
        "/api/chat/stream",
        json={"device_id": "device-sync", "message": "open settings"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    assert "event: error" in body
    assert "does not support streaming" in body


def test_get_config_masks_empty_api_key_and_maps_conflicts(
    env: dict[str, Any],
) -> None:
    env["config_manager"].conflicts = [
        SimpleNamespace(
            field="base_url",
            file_value="http://file",
            override_value="http://env",
            override_source=SimpleNamespace(value="environment variables"),
        )
    ]

    response = env["client"].get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"] == ""
    assert payload["source"] == "config file (~/.config/autoglm/config.json)"
    assert payload["conflicts"] == [
        {
            "field": "base_url",
            "file_value": "http://file",
            "override_value": "http://env",
            "override_source": "environment variables",
        }
    ]


def test_save_config_success_with_warnings_and_restart_required(
    env: dict[str, Any],
) -> None:
    env["config_manager"].conflicts = [
        SimpleNamespace(
            field="model_name",
            file_value="A",
            override_value="B",
            override_source=SimpleNamespace(value="CLI arguments"),
        )
    ]
    response = env["client"].post(
        "/api/config",
        json={
            "base_url": "http://localhost:8080/v1",
            "model_name": "autoglm-phone-9b",
            "api_key": "token",
            "default_max_steps": 80,
            "layered_max_turns": 40,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["restart_required"] is True
    assert "warnings" in payload
    assert env["config_manager"].sync_called is True
    assert env["config_manager"].save_kwargs is not None
    assert env["config_manager"].save_kwargs["merge_mode"] is True
    assert env["phone_manager"].destroy_calls == []


def test_save_config_returns_500_when_persist_fails(env: dict[str, Any]) -> None:
    env["config_manager"].save_result = False

    response = env["client"].post(
        "/api/config",
        json={
            "base_url": "http://localhost:8080/v1",
            "model_name": "autoglm-phone-9b",
            "api_key": "token",
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "500: Failed to save config"


def test_delete_config_success_and_failure(env: dict[str, Any]) -> None:
    success_resp = env["client"].delete("/api/config")
    assert success_resp.status_code == 200
    assert success_resp.json() == {"success": True, "message": "Configuration deleted"}

    env["config_manager"].delete_result = False
    failed_resp = env["client"].delete("/api/config")
    assert failed_resp.status_code == 500
    assert failed_resp.json()["detail"] == "500: Failed to delete config"
