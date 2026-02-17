"""Unit tests for DeviceManager ADB Keyboard one-time setup behavior."""

from __future__ import annotations

import pytest

import AutoGLM_GUI.adb_plus as adb_plus_module
import AutoGLM_GUI.device_manager as device_manager_module
import AutoGLM_GUI.device_metadata_manager as device_metadata_manager_module
from AutoGLM_GUI.types import DeviceConnectionType


class _FakeMetadataManager:
    def get_display_name(self, serial: str) -> str | None:  # noqa: ARG002
        return None


class _FakeInstaller:
    calls: list[tuple[str, str]] = []
    status = {"installed": False, "enabled": False}
    setup_result: tuple[bool, str] = (True, "ok")
    raise_on_setup = False

    def __init__(self, device_id: str | None = None):
        self.device_id = device_id or ""
        self.__class__.calls.append(("init", self.device_id))

    def get_status(self) -> dict:
        self.__class__.calls.append(("status", self.device_id))
        return dict(self.__class__.status)

    def auto_setup(self) -> tuple[bool, str]:
        self.__class__.calls.append(("setup", self.device_id))
        if self.__class__.raise_on_setup:
            raise RuntimeError("setup failed")
        return self.__class__.setup_result


def _build_local_managed(
    serial: str, device_id: str
) -> device_manager_module.ManagedDevice:
    return device_manager_module.ManagedDevice(
        serial=serial,
        connections=[
            device_manager_module.DeviceConnection(
                device_id=device_id,
                connection_type=DeviceConnectionType.USB,
                status="device",
            )
        ],
    )


def _build_remote_managed(
    serial: str, device_id: str
) -> device_manager_module.ManagedDevice:
    return device_manager_module.ManagedDevice(
        serial=serial,
        connections=[
            device_manager_module.DeviceConnection(
                device_id=device_id,
                connection_type=DeviceConnectionType.REMOTE,
                status="device",
            )
        ],
    )


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> device_manager_module.DeviceManager:
    monkeypatch.setattr(
        device_metadata_manager_module.DeviceMetadataManager,
        "get_instance",
        staticmethod(lambda: _FakeMetadataManager()),
    )
    return device_manager_module.DeviceManager(adb_path="adb")


@pytest.fixture(autouse=True)
def reset_fake_installer(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeInstaller.calls = []
    _FakeInstaller.status = {"installed": False, "enabled": False}
    _FakeInstaller.setup_result = (True, "ok")
    _FakeInstaller.raise_on_setup = False
    monkeypatch.setattr(adb_plus_module, "ADBKeyboardInstaller", _FakeInstaller)


def test_local_device_triggers_setup_once_on_first_protocol_access(
    manager: device_manager_module.DeviceManager,
) -> None:
    managed = _build_local_managed(serial="SER-1", device_id="dev-1")
    manager._devices["SER-1"] = managed
    manager._device_id_to_serial["dev-1"] = "SER-1"

    manager.get_device_protocol("dev-1")

    assert ("status", "dev-1") in _FakeInstaller.calls
    assert ("setup", "dev-1") in _FakeInstaller.calls
    assert "SER-1" in manager._adb_keyboard_attempted_serials
    assert "SER-1" in manager._adb_keyboard_ready_serials


def test_same_serial_second_access_does_not_trigger_second_setup(
    manager: device_manager_module.DeviceManager,
) -> None:
    managed = _build_local_managed(serial="SER-2", device_id="dev-2")
    manager._devices["SER-2"] = managed
    manager._device_id_to_serial["dev-2"] = "SER-2"

    manager.get_device_protocol("dev-2")
    manager.get_device_protocol("dev-2")

    assert _FakeInstaller.calls.count(("status", "dev-2")) == 1
    assert _FakeInstaller.calls.count(("setup", "dev-2")) == 1


def test_remote_device_does_not_trigger_adb_keyboard_setup(
    manager: device_manager_module.DeviceManager,
) -> None:
    remote = object()
    managed = _build_remote_managed(
        serial="remote:http://127.0.0.1:9000:dev-remote",
        device_id="http://127.0.0.1:9000|dev-remote",
    )
    manager._devices[managed.serial] = managed
    manager._device_id_to_serial[managed.primary_device_id] = managed.serial
    manager._remote_devices[managed.serial] = remote  # type: ignore[assignment]

    protocol = manager.get_device_protocol(managed.primary_device_id)

    assert protocol is remote
    assert _FakeInstaller.calls == []


def test_setup_failure_does_not_raise_and_still_returns_local_protocol(
    manager: device_manager_module.DeviceManager,
) -> None:
    managed = _build_local_managed(serial="SER-3", device_id="dev-3")
    manager._devices["SER-3"] = managed
    manager._device_id_to_serial["dev-3"] = "SER-3"
    _FakeInstaller.raise_on_setup = True

    protocol = manager.get_device_protocol("dev-3")

    from AutoGLM_GUI.devices.adb_device import ADBDevice

    assert isinstance(protocol, ADBDevice)
    assert "SER-3" in manager._adb_keyboard_attempted_serials
    assert "SER-3" not in manager._adb_keyboard_ready_serials
    assert _FakeInstaller.calls.count(("setup", "dev-3")) == 1
