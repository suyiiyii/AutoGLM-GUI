"""Device implementations for the DeviceProtocol interface.

This package provides concrete implementations of DeviceProtocol:
- ADBDevice: Local ADB subprocess calls
- MockDevice: State machine driven mock for testing
- RemoteDevice: HTTP client for remote device agents

Example:
    >>> from AutoGLM_GUI.devices import ADBDevice, RemoteDevice, get_device_manager
    >>>
    >>> # Local ADB device
    >>> device = ADBDevice("emulator-5554")
    >>> device.tap(100, 200)
    >>>
    >>> # Remote device via HTTP
    >>> remote = RemoteDevice("phone_001", "http://device-agent:8001")
    >>> remote.tap(100, 200)
"""

from AutoGLM_GUI.devices.adb_device import ADBDevice, ADBDeviceManager
from AutoGLM_GUI.devices.mock_device import MockDevice
from AutoGLM_GUI.devices.remote_device import RemoteDevice, RemoteDeviceManager

_device_manager: "ADBDeviceManager | None" = None


def get_device_manager() -> ADBDeviceManager:
    """Get the global device manager instance."""
    global _device_manager
    if _device_manager is None:
        _device_manager = ADBDeviceManager()
    return _device_manager


def set_device_manager(manager: "ADBDeviceManager") -> None:
    """Set the global device manager instance (useful for testing)."""
    global _device_manager
    _device_manager = manager


__all__ = [
    "ADBDevice",
    "ADBDeviceManager",
    "MockDevice",
    "RemoteDevice",
    "RemoteDeviceManager",
    "get_device_manager",
    "set_device_manager",
]
