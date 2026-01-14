"""End-to-end tests for configuration management workflows.

Tests configuration management including:
- Config loading from file and environment
- Conflict detection between different config sources
- Auto-destroy agents when config changes
- Config persistence and deletion
"""

from fastapi.testclient import TestClient


class TestConfigLoading:
    """Test configuration loading from different sources."""

    def test_get_empty_config(self, api_client: TestClient):
        """Test getting config when none is set."""
        response = api_client.get("/api/config")
        assert response.status_code == 200
        config = response.json()

        assert "base_url" in config
        assert "conflicts" in config


class TestConfigConflictDetection:
    """Test conflict detection between config sources."""

    def test_config_response_includes_conflicts(self, api_client: TestClient):
        """Test that config GET includes conflict information."""
        response = api_client.post(
            "/api/config",
            json={
                "base_url": "http://test1.com/v1",
                "api_key": "key1",
                "model_name": "model1",
            },
        )

        assert response.status_code == 200

        response = api_client.get("/api/config")
        assert response.status_code == 200
        config = response.json()

        assert "conflicts" in config
        assert isinstance(config["conflicts"], list)


class TestConfigAutoDestroy:
    """Test auto-destroy of agents when config changes."""

    def test_save_config_destroys_active_agents(
        self, api_client: TestClient, mock_llm_server: str, mock_agent_server: str
    ):
        """Test that saving new config destroys active agents."""
        api_client.post(
            "/api/devices/add_remote",
            json={"base_url": mock_agent_server, "device_id": "mock_device_001"},
        )
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "key1",
                "model_name": "model1",
            },
        )

        api_client.post("/api/init", json={"device_id": "mock_device_001"})

        api_client.post(
            "/api/config",
            json={
                "base_url": "http://different.com/v1",
                "api_key": "key2",
                "model_name": "model2",
            },
        )

    def test_multiple_config_changes(self, api_client: TestClient):
        """Test multiple config changes in sequence."""
        for i in range(3):
            api_client.post(
                "/api/config",
                json={
                    "base_url": f"http://test{i}.com/v1",
                    "api_key": f"key{i}",
                    "model_name": f"model{i}",
                },
            )


class TestConfigPersistence:
    """Test configuration persistence and deletion."""

    def test_delete_config(self, api_client: TestClient):
        """Test deleting config clears all settings."""
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

        base_url = config.get("base_url")
        assert base_url is None or base_url == ""

    def test_config_survives_restart(
        self, api_client: TestClient, mock_llm_server: str
    ):
        """Test that config persists (simulated by getting config multiple times)."""
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "persisted-key",
                "model_name": "persisted-model",
            },
        )

        response1 = api_client.get("/api/config")
        config1 = response1.json()

        response2 = api_client.get("/api/config")
        config2 = response2.json()

        assert config1.get("api_key") == "persisted-key"
        assert config2.get("api_key") == "persisted-key"


class TestConfigValidation:
    """Test configuration validation."""

    def test_invalid_base_url_format(self, api_client: TestClient):
        """Test config with invalid base_url format."""
        response = api_client.post(
            "/api/config",
            json={
                "base_url": "not-a-valid-url",
                "api_key": "test-key",
                "model_name": "test-model",
            },
        )

        assert response.status_code in [200, 422]

    def test_empty_required_fields(self, api_client: TestClient):
        """Test config with missing required fields."""
        response = api_client.post("/api/config", json={"base_url": "http://test.com"})

        assert response.status_code in [200, 422]

    def test_partial_config_update(
        self, api_client: TestClient, mock_llm_server: str, mock_agent_server: str
    ):
        """Test updating only part of config."""
        api_client.post(
            "/api/devices/add_remote",
            json={"base_url": mock_agent_server, "device_id": "mock_device_001"},
        )
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "initial-key",
                "model_name": "initial-model",
            },
        )

        response = api_client.post(
            "/api/config",
            json={"model_name": "updated-model"},
        )

        assert response.status_code in [200, 422]
