"""Unit tests for persisted remote device registrations."""

from __future__ import annotations

import pytest

import AutoGLM_GUI.device_manager as device_manager_module
import AutoGLM_GUI.device_metadata_manager as device_metadata_manager_module
import AutoGLM_GUI.remote_device_registry_manager as remote_registry_module
from AutoGLM_GUI.types import DeviceConnectionType


class _FakeMetadataManager:
    def get_display_name(self, serial: str) -> str | None:  # noqa: ARG002
        return None


class _FakeRegistryManager:
    def __init__(self, initial: dict[str, dict[str, str]] | None = None) -> None:
        self.configs = dict(initial or {})
        self.set_calls: list[tuple[str, str, str]] = []
        self.remove_calls: list[str] = []

    def list_configs(self) -> dict[str, dict[str, str]]:
        return {serial: dict(config) for serial, config in self.configs.items()}

    def set_config(self, serial: str, *, base_url: str, device_id: str) -> None:
        self.configs[serial] = {"base_url": base_url, "device_id": device_id}
        self.set_calls.append((serial, base_url, device_id))

    def remove_config(self, serial: str) -> None:
        self.configs.pop(serial, None)
        self.remove_calls.append(serial)


class _FakeRemoteDevice:
    attempts: dict[str, int] = {}
    failures_before_success: dict[str, int] = {}

    def __init__(self, device_id: str, base_url: str, timeout: float = 30.0):  # noqa: ARG002
        self.device_id = device_id
        self.base_url = base_url.rstrip("/")

    def get_screenshot(self, timeout: int = 5) -> object:  # noqa: ARG002
        key = f"{self.base_url}|{self.device_id}"
        count = self.__class__.attempts.get(key, 0) + 1
        self.__class__.attempts[key] = count
        required_failures = self.__class__.failures_before_success.get(key, 0)
        if count <= required_failures:
            raise RuntimeError("remote offline")
        return object()

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def reset_fakes() -> None:
    _FakeRemoteDevice.attempts = {}
    _FakeRemoteDevice.failures_before_success = {}


def test_add_and_remove_remote_device_updates_persistent_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _FakeRegistryManager()
    monkeypatch.setattr(
        device_metadata_manager_module.DeviceMetadataManager,
        "get_instance",
        staticmethod(lambda: _FakeMetadataManager()),
    )
    monkeypatch.setattr(
        remote_registry_module.RemoteDeviceRegistryManager,
        "get_instance",
        staticmethod(lambda: registry),
    )
    monkeypatch.setattr(
        "AutoGLM_GUI.devices.remote_device.RemoteDevice", _FakeRemoteDevice
    )

    manager = device_manager_module.DeviceManager(adb_path="adb")
    success, _, serial = manager.add_remote_device("http://remote.test", "device-1")

    assert success is True
    assert serial == "remote:http://remote.test:device-1"
    assert registry.set_calls == [
        ("remote:http://remote.test:device-1", "http://remote.test", "device-1")
    ]

    removed, _ = manager.remove_remote_device(serial)

    assert removed is True
    assert registry.remove_calls == [serial]


def test_force_refresh_restores_persisted_remote_device_after_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial = "remote:http://remote.test:device-1"
    registry = _FakeRegistryManager(
        {
            serial: {
                "base_url": "http://remote.test",
                "device_id": "device-1",
            }
        }
    )
    _FakeRemoteDevice.failures_before_success["http://remote.test|device-1"] = 1

    monkeypatch.setattr(
        device_metadata_manager_module.DeviceMetadataManager,
        "get_instance",
        staticmethod(lambda: _FakeMetadataManager()),
    )
    monkeypatch.setattr(
        remote_registry_module.RemoteDeviceRegistryManager,
        "get_instance",
        staticmethod(lambda: registry),
    )
    monkeypatch.setattr(
        "AutoGLM_GUI.devices.remote_device.RemoteDevice", _FakeRemoteDevice
    )
    monkeypatch.setattr(
        device_manager_module.ADBConnection,
        "list_devices",
        lambda self: [],
    )

    manager = device_manager_module.DeviceManager(adb_path="adb")

    placeholder = manager.get_device_by_serial(serial)
    assert placeholder is not None
    assert placeholder.connection_type == DeviceConnectionType.REMOTE
    assert placeholder.status == "offline"
    assert serial not in manager._remote_devices

    manager.force_refresh()

    restored = manager.get_device_by_serial(serial)
    assert restored is not None
    assert restored.connection_type == DeviceConnectionType.REMOTE
    assert restored.primary_device_id == "http://remote.test|device-1"
    assert serial in manager._remote_devices
    assert _FakeRemoteDevice.attempts["http://remote.test|device-1"] == 2
