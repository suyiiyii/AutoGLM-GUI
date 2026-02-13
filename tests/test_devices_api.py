"""Contract tests for device discovery/connection API endpoints."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.adb as adb_module
import AutoGLM_GUI.adb_plus as adb_plus_module
import AutoGLM_GUI.api.devices as devices_api
import AutoGLM_GUI.device_group_manager as device_group_manager_module
import AutoGLM_GUI.device_manager as device_manager_module
import AutoGLM_GUI.phone_agent_manager as phone_agent_manager_module

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeConnection:
    def __init__(self, device_id: str) -> None:
        self.device_id = device_id


class FakeManagedDevice:
    def __init__(
        self,
        *,
        device_id: str = "dev-1",
        serial: str = "SER-1",
        model: str = "Pixel 8",
    ) -> None:
        self.serial = serial
        self.connections = [FakeConnection(device_id)]
        self._device_id = device_id
        self._model = model

    def to_dict(self) -> dict:
        return {
            "id": self._device_id,
            "serial": self.serial,
            "model": self._model,
            "status": "device",
            "connection_type": "usb",
            "state": "online",
            "is_available_only": False,
            "display_name": None,
        }


class FakeDeviceGroupManager:
    def __init__(self) -> None:
        self.group_map: dict[str, str] = {}

    def get_device_group(self, serial: str) -> str:
        return self.group_map.get(serial, "default")


class FakeMetadata:
    def __init__(self, model_name: str = "glm-async") -> None:
        self.state = "idle"
        self.created_at = 1700000000.0
        self.last_used = 1700000001.0
        self.error_message = None
        self.model_config = SimpleNamespace(model_name=model_name)


class FakePhoneAgentManager:
    def __init__(self) -> None:
        self.metadata_by_device_id: dict[str, FakeMetadata] = {}

    def get_metadata(self, device_id: str) -> FakeMetadata | None:
        return self.metadata_by_device_id.get(device_id)


class FakeDeviceManager:
    def __init__(self) -> None:
        self.polling_active = True
        self.force_refresh_calls = 0
        self.devices = [FakeManagedDevice(device_id="dev-1", serial="SER-1")]

        self.connect_wifi_result = (True, "Connected", "192.168.0.20:5555")
        self.disconnect_wifi_result = (True, "Disconnected")
        self.connect_wifi_manual_result = (True, "Connected", "10.0.0.10:5555")
        self.pair_wifi_result = (True, "Paired", "10.0.0.10:5555")
        self.discover_remote_result = (
            True,
            "ok",
            [
                {
                    "device_id": "remote-1",
                    "model": "RemotePhone",
                    "platform": "android",
                    "status": "online",
                }
            ],
        )
        self.add_remote_result = (True, "Added", "remote-serial-1")
        self.remove_remote_result = (True, "Removed")

        self.last_connect_wifi_args: tuple[str, int] | None = None
        self.last_disconnect_wifi_device: str | None = None
        self.last_connect_wifi_manual_args: tuple[str, int] | None = None
        self.last_pair_wifi_args: tuple[str, int, str, int] | None = None

    def is_polling_active(self) -> bool:
        return self.polling_active

    def force_refresh(self) -> None:
        self.force_refresh_calls += 1

    def get_devices(self) -> list[FakeManagedDevice]:
        return self.devices

    def connect_wifi(self, device_id: str, port: int) -> tuple[bool, str, str | None]:
        self.last_connect_wifi_args = (device_id, port)
        return self.connect_wifi_result

    def disconnect_wifi(self, device_id: str) -> tuple[bool, str]:
        self.last_disconnect_wifi_device = device_id
        return self.disconnect_wifi_result

    def connect_wifi_manual(self, ip: str, port: int) -> tuple[bool, str, str | None]:
        self.last_connect_wifi_manual_args = (ip, port)
        return self.connect_wifi_manual_result

    def pair_wifi(
        self, ip: str, pairing_port: int, pairing_code: str, connection_port: int
    ) -> tuple[bool, str, str | None]:
        self.last_pair_wifi_args = (ip, pairing_port, pairing_code, connection_port)
        return self.pair_wifi_result

    def discover_remote_devices(
        self, base_url: str, timeout: int
    ) -> tuple[bool, str, list[dict]]:
        _ = (base_url, timeout)
        return self.discover_remote_result

    def add_remote_device(
        self, base_url: str, device_id: str
    ) -> tuple[bool, str, str | None]:
        _ = (base_url, device_id)
        return self.add_remote_result

    def remove_remote_device(self, serial: str) -> tuple[bool, str]:
        _ = serial
        return self.remove_remote_result


@pytest.fixture
def devices_env(monkeypatch: pytest.MonkeyPatch) -> dict:
    fake_device_manager = FakeDeviceManager()
    fake_agent_manager = FakePhoneAgentManager()
    fake_group_manager = FakeDeviceGroupManager()

    monkeypatch.setattr(
        device_manager_module.DeviceManager,
        "get_instance",
        staticmethod(lambda: fake_device_manager),
    )
    monkeypatch.setattr(
        phone_agent_manager_module.PhoneAgentManager,
        "get_instance",
        staticmethod(lambda: fake_agent_manager),
    )
    monkeypatch.setattr(
        device_group_manager_module, "device_group_manager", fake_group_manager
    )

    app = FastAPI()
    app.include_router(devices_api.router)
    client = TestClient(app)

    return {
        "client": client,
        "device_manager": fake_device_manager,
        "agent_manager": fake_agent_manager,
        "group_manager": fake_group_manager,
    }


def test_list_devices_refreshes_when_polling_inactive(devices_env: dict) -> None:
    devices_env["device_manager"].polling_active = False
    devices_env["group_manager"].group_map["SER-1"] = "qa"
    devices_env["agent_manager"].metadata_by_device_id["dev-1"] = FakeMetadata(
        model_name="autoglm-phone-9b"
    )

    response = devices_env["client"].get("/api/devices")

    assert response.status_code == 200
    assert devices_env["device_manager"].force_refresh_calls == 1
    device = response.json()["devices"][0]
    assert device["group_id"] == "qa"
    assert device["agent"]["state"] == "idle"
    assert device["agent"]["model_name"] == "autoglm-phone-9b"


def test_connect_wifi_requires_device_id(devices_env: dict) -> None:
    response = devices_env["client"].post(
        "/api/devices/connect_wifi", json={"port": 5555}
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "device_id is required",
        "device_id": None,
        "address": None,
        "error": "device_not_found",
    }


def test_connect_wifi_success_returns_address_and_refreshes(devices_env: dict) -> None:
    response = devices_env["client"].post(
        "/api/devices/connect_wifi",
        json={"device_id": "usb-1", "port": 5555},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Connected",
        "device_id": "192.168.0.20:5555",
        "address": "192.168.0.20:5555",
        "error": None,
    }
    assert devices_env["device_manager"].last_connect_wifi_args == ("usb-1", 5555)
    assert devices_env["device_manager"].force_refresh_calls == 1


def test_connect_wifi_failure_maps_not_found_error(devices_env: dict) -> None:
    devices_env["device_manager"].connect_wifi_result = (
        False,
        "Device not found",
        None,
    )

    response = devices_env["client"].post(
        "/api/devices/connect_wifi",
        json={"device_id": "usb-missing", "port": 5555},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "device_not_found"


def test_disconnect_wifi_success_refreshes(devices_env: dict) -> None:
    response = devices_env["client"].post(
        "/api/devices/disconnect_wifi",
        json={"device_id": "192.168.0.20:5555"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Disconnected",
        "error": None,
    }
    assert (
        devices_env["device_manager"].last_disconnect_wifi_device == "192.168.0.20:5555"
    )
    assert devices_env["device_manager"].force_refresh_calls == 1


def test_connect_wifi_manual_failure_maps_invalid_ip(devices_env: dict) -> None:
    devices_env["device_manager"].connect_wifi_manual_result = (
        False,
        "Invalid IP address",
        None,
    )

    response = devices_env["client"].post(
        "/api/devices/connect_wifi_manual",
        json={"ip": "10.0.0.2", "port": 5555},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "Invalid IP address",
        "device_id": None,
        "error": "invalid_ip",
    }


def test_pair_wifi_failure_maps_invalid_pairing_code(devices_env: dict) -> None:
    devices_env["device_manager"].pair_wifi_result = (
        False,
        "Pairing code must be 6 digits",
        None,
    )

    response = devices_env["client"].post(
        "/api/devices/pair_wifi",
        json={
            "ip": "10.0.0.3",
            "pairing_port": 37099,
            "pairing_code": "123456",
            "connection_port": 5555,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "Pairing code must be 6 digits",
        "device_id": None,
        "error": "invalid_pairing_code",
    }


def test_discover_remote_devices_returns_manager_payload(devices_env: dict) -> None:
    response = devices_env["client"].post(
        "/api/devices/discover_remote",
        json={"base_url": "http://127.0.0.1:9000", "timeout": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "ok"
    assert len(body["devices"]) == 1
    assert body["devices"][0]["device_id"] == "remote-1"


def test_add_remote_device_failure_maps_already_exists(devices_env: dict) -> None:
    devices_env["device_manager"].add_remote_result = (
        False,
        "Device already exists",
        None,
    )

    response = devices_env["client"].post(
        "/api/devices/add_remote",
        json={"base_url": "http://127.0.0.1:9000", "device_id": "remote-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "Device already exists",
        "serial": None,
        "error": "already_exists",
    }


def test_remove_remote_device_failure_returns_remove_failed(devices_env: dict) -> None:
    devices_env["device_manager"].remove_remote_result = (False, "Serial not found")

    response = devices_env["client"].post(
        "/api/devices/remove_remote",
        json={"serial": "missing-serial"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "Serial not found",
        "error": "remove_failed",
    }


def test_discover_mdns_success(
    monkeypatch: pytest.MonkeyPatch, devices_env: dict
) -> None:
    class FakeADBConnection:
        adb_path = "/tmp/fake-adb"

    def fake_discover_mdns_devices(adb_path: str) -> list[SimpleNamespace]:
        assert adb_path == "/tmp/fake-adb"
        return [
            SimpleNamespace(
                name="adb-001",
                ip="192.168.0.30",
                port=5555,
                has_pairing=True,
                service_type="_adb._tcp",
                pairing_port=37123,
            )
        ]

    monkeypatch.setattr(adb_module, "ADBConnection", FakeADBConnection)
    monkeypatch.setattr(
        adb_plus_module, "discover_mdns_devices", fake_discover_mdns_devices
    )

    response = devices_env["client"].get("/api/devices/discover_mdns")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["devices"][0]["name"] == "adb-001"
    assert body["devices"][0]["pairing_port"] == 37123


def test_discover_mdns_exception_returns_error(
    monkeypatch: pytest.MonkeyPatch, devices_env: dict
) -> None:
    class FakeADBConnection:
        adb_path = "/tmp/fake-adb"

    def broken_discover_mdns_devices(adb_path: str) -> list[SimpleNamespace]:
        _ = adb_path
        raise RuntimeError("mDNS backend unavailable")

    monkeypatch.setattr(adb_module, "ADBConnection", FakeADBConnection)
    monkeypatch.setattr(
        adb_plus_module, "discover_mdns_devices", broken_discover_mdns_devices
    )

    response = devices_env["client"].get("/api/devices/discover_mdns")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["devices"] == []
    assert body["error"] == "mDNS backend unavailable"
