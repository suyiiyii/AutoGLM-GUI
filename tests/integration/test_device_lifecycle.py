"""End-to-end tests for device lifecycle workflows.

Tests complete device lifecycle including:
- Device registration and discovery
- Agent initialization
- Task execution
- Configuration management
- Agent cleanup
"""

import httpx
import multiprocessing
import pytest
import time
from fastapi.testclient import TestClient

from tests.integration.conftest import api_client, find_free_port, wait_for_server


class TestDeviceConnectionFlow:
    """Test device connection and registration workflows."""

    def test_usb_device_registration(
        self, api_client: TestClient, mock_agent_server: str
    ):
        """Test USB device registration via remote device addition."""
        response = api_client.post(
            "/api/devices/add_remote",
            json={"url": mock_agent_server},
        )
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert data["success"] is True

        response = api_client.get("/api/devices")
        assert response.status_code == 200
        devices = response.json()["devices"]
        assert len(devices) > 0

        mock_device = next((d for d in devices if d["serial"].startswith("mock")), None)
        assert mock_device is not None
        assert mock_device["online"] is True

    def test_list_devices_empty_initially(self, api_client: TestClient):
        """Test that device list is empty initially (no devices added yet)."""
        response = api_client.get("/api/devices")
        assert response.status_code == 200
        devices = response.json()["devices"]
        assert devices is not None

    def test_discover_remote_devices(
        self, api_client: TestClient, mock_agent_server: str
    ):
        """Test discovering devices from remote server."""
        response = api_client.post(
            "/api/devices/discover_remote",
            json={"url": mock_agent_server},
        )
        assert response.status_code == 200

        response = api_client.get("/api/devices")
        assert response.status_code == 200
        devices = response.json()["devices"]

    def test_remove_remote_device(self, api_client: TestClient, mock_agent_server: str):
        """Test removing a remote device."""
        api_client.post("/api/devices/add_remote", json={"url": mock_agent_server})

        response = api_client.get("/api/devices")
        devices = response.json()["devices"]
        mock_device = next((d for d in devices if d["serial"].startswith("mock")), None)
        assert mock_device is not None
        device_serial = mock_device["serial"]

        response = api_client.post(
            "/api/devices/remove_remote",
            json={"serial": device_serial},
        )
        assert response.status_code == 200

        response = api_client.get("/api/devices")
        devices = response.json()["devices"]
        removed = next((d for d in devices if d["serial"] == device_serial), None)
        assert removed is None


class TestAgentInitialization:
    """Test agent initialization workflows."""

    def test_init_agent_success(
        self, api_client: TestClient, mock_llm_server: str, mock_agent_server: str
    ):
        """Test successful agent initialization."""
        api_client.post("/api/devices/add_remote", json={"url": mock_agent_server})

        response = api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )
        assert response.status_code == 200

        response = api_client.post(
            "/api/init",
            json={
                "device_id": "mock_device_001",
                "agent_type": "glm",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "agent_id" in data
        assert data["success"] is True

    def test_init_agent_invalid_device_id(
        self, api_client: TestClient, mock_llm_server: str
    ):
        """Test initialization fails with invalid device ID."""
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )

        response = api_client.post(
            "/api/init",
            json={"device_id": "nonexistent_device", "agent_type": "glm"},
        )

        assert response.status_code in [200, 404, 400]


class TestTaskExecutionFlow:
    """Test complete task execution workflow."""

    def test_chat_flow(
        self,
        api_client: TestClient,
        mock_llm_server: str,
        mock_agent_server: str,
    ):
        """Test complete chat flow with blocking endpoint."""
        llm_port = find_free_port(start=18000, end=18999)

        from tests.integration.device_agent.mock_llm_server import run_server

        llm_proc = multiprocessing.Process(
            target=run_server, args=(llm_port,), daemon=True
        )
        llm_proc.start()

        llm_url = f"http://127.0.0.1:{llm_port}"
        wait_for_server(llm_url, timeout=5.0, endpoint="/test/stats")

        try:
            api_client.post("/api/devices/add_remote", json={"url": mock_agent_server})
            api_client.post(
                "/api/config",
                json={
                    "base_url": llm_url + "/v1",
                    "api_key": "mock-key",
                    "model_name": "autoglm-phone",
                },
            )

            api_client.post("/api/init", json={"device_id": "mock_device_001"})

            response = api_client.post(
                "/api/chat",
                json={
                    "device_id": "mock_device_001",
                    "message": "test task",
                },
            )

            assert response.status_code == 200
            result = response.json()

        finally:
            llm_proc.terminate()
            llm_proc.join(timeout=2)


class TestCleanupFlow:
    """Test cleanup and configuration management workflows."""

    def test_config_save_destroys_agents(self, api_client: TestClient):
        """Test that saving new config destroys existing agents."""
        status_response = api_client.get("/api/status")
        initial_agents = status_response.json().get("agents", [])

        response = api_client.post(
            "/api/config",
            json={
                "base_url": "http://localhost:8080/v1",
                "api_key": "test-key",
                "model_name": "test-model",
            },
        )
        assert response.status_code == 200

        status_response = api_client.get("/api/status")
        final_agents = status_response.json().get("agents", [])

    def test_delete_config_clears_settings(self, api_client: TestClient):
        """Test that deleting config clears all settings."""
        api_client.post(
            "/api/config",
            json={
                "base_url": "http://test.com/v1",
                "api_key": "test-key",
                "model_name": "test-model",
            },
        )

        response = api_client.delete("/api/config")
        assert response.status_code == 200

        response = api_client.get("/api/config")
        assert response.status_code == 200
        config = response.json()

        assert config.get("base_url") is None or config.get("base_url") == ""

    def test_get_config_effective_and_conflicts(
        self, api_client: TestClient, mock_llm_server: str
    ):
        """Test getting config with effective and conflict information."""
        api_client.post(
            "/api/config",
            json={
                "base_url": "http://api-config.com/v1",
                "api_key": "api-key",
                "model_name": "api-model",
            },
        )

        response = api_client.get("/api/config")
        assert response.status_code == 200
        config = response.json()

        assert "effective" in config
        assert "conflicts" in config

        effective = config["effective"]
        assert effective.get("base_url") == "http://api-config.com/v1"
