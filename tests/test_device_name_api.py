"""Integration tests for device name API endpoints."""

import pytest
from fastapi.testclient import TestClient

from AutoGLM_GUI.api import create_app
from AutoGLM_GUI.device_metadata_manager import (
    DISPLAY_NAME_MAX_LENGTH,
    DeviceMetadataManager,
)


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_manager():
    """Reset DeviceMetadataManager singleton before each test."""
    DeviceMetadataManager._instance = None
    yield
    DeviceMetadataManager._instance = None


def test_get_device_name_not_found(client):
    """Test GET /api/devices/{serial}/name returns None for unknown device."""
    response = client.get("/api/devices/unknown_device/name")
    assert response.status_code == 200
    data = response.json()
    assert data["serial"] == "unknown_device"
    assert data["display_name"] is None


def test_set_and_get_device_name(client):
    """Test PUT and GET device name endpoints."""
    serial = "test_device_001"
    display_name = "My Test Device"

    response = client.put(
        f"/api/devices/{serial}/name", json={"display_name": display_name}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["serial"] == serial
    assert data["display_name"] == display_name

    response = client.get(f"/api/devices/{serial}/name")
    assert response.status_code == 200
    data = response.json()
    assert data["serial"] == serial
    assert data["display_name"] == display_name


def test_set_device_name_empty_string_clears(client):
    """Test that empty string clears device name."""
    serial = "test_device_002"

    client.put(f"/api/devices/{serial}/name", json={"display_name": "Initial Name"})

    response = client.put(f"/api/devices/{serial}/name", json={"display_name": ""})
    assert response.status_code == 200
    assert response.json()["display_name"] is None

    response = client.get(f"/api/devices/{serial}/name")
    assert response.status_code == 200
    assert response.json()["display_name"] is None


def test_set_device_name_whitespace_only_clears(client):
    """Test that whitespace-only string clears device name."""
    serial = "test_device_003"

    client.put(f"/api/devices/{serial}/name", json={"display_name": "Initial Name"})

    response = client.put(f"/api/devices/{serial}/name", json={"display_name": "   "})
    assert response.status_code == 200
    assert response.json()["display_name"] is None


def test_set_device_name_too_long_rejected(client):
    """Test that name exceeding max length is rejected."""
    serial = "test_device_004"
    too_long_name = "a" * (DISPLAY_NAME_MAX_LENGTH + 1)

    response = client.put(
        f"/api/devices/{serial}/name", json={"display_name": too_long_name}
    )
    assert response.status_code == 422


def test_set_device_name_max_length_accepted(client):
    """Test that name at max length is accepted."""
    serial = "test_device_005"
    max_length_name = "a" * DISPLAY_NAME_MAX_LENGTH

    response = client.put(
        f"/api/devices/{serial}/name", json={"display_name": max_length_name}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == max_length_name


def test_devices_list_includes_display_name(client):
    """Test that GET /api/devices includes display_name in response."""
    serial = "test_device_006"
    display_name = "Device With Name"

    client.put(f"/api/devices/{serial}/name", json={"display_name": display_name})

    response = client.get("/api/devices")
    assert response.status_code == 200

    devices = response.json()["devices"]

    matching_device = next((d for d in devices if d["serial"] == serial), None)
    if matching_device:
        assert "display_name" in matching_device
        assert matching_device["display_name"] == display_name


def test_set_device_name_idempotent(client):
    """Test that setting the same name twice doesn't cause issues."""
    serial = "test_device_007"
    display_name = "Same Name"

    response1 = client.put(
        f"/api/devices/{serial}/name", json={"display_name": display_name}
    )
    assert response1.status_code == 200

    response2 = client.put(
        f"/api/devices/{serial}/name", json={"display_name": display_name}
    )
    assert response2.status_code == 200
    assert response2.json()["display_name"] == display_name


def test_set_device_name_update_existing(client):
    """Test updating an existing device name."""
    serial = "test_device_008"

    response = client.put(
        f"/api/devices/{serial}/name", json={"display_name": "Old Name"}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Old Name"

    response = client.put(
        f"/api/devices/{serial}/name", json={"display_name": "New Name"}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "New Name"

    response = client.get(f"/api/devices/{serial}/name")
    assert response.status_code == 200
    assert response.json()["display_name"] == "New Name"


def test_all_responses_include_success_field(client):
    """Test that all device name responses include success field."""
    serial = "test_device_009"

    response = client.put(
        f"/api/devices/{serial}/name", json={"display_name": "Test Name"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert data["success"] is True
    assert data["serial"] == serial

    response = client.get(f"/api/devices/{serial}/name")
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert data["success"] is True

    response = client.get("/api/devices/nonexistent_device/name")
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert data["success"] is True
