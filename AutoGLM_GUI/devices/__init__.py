"""Device implementations for the DeviceProtocol interface.

This package provides concrete implementations of DeviceProtocol:
- ADBDevice: Local ADB subprocess calls
- MockDevice: State machine driven mock for testing
- RemoteDevice: HTTP/gRPC client for remote device agents (future)

Example:
    >>> from AutoGLM_GUI.devices import ADBDevice, MockDevice, get_device_manager
    >>>
    >>> # Get the global device manager
    >>> manager = get_device_manager()
    >>> devices = manager.list_devices()
    >>>
    >>> # Or create a device directly
    >>> device = ADBDevice("emulator-5554")
    >>> device.tap(100, 200)
"""

from AutoGLM_GUI.devices.adb_device import ADBDevice, ADBDeviceManager
from AutoGLM_GUI.devices.mock_device import MockDevice

# Global device manager instance
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
    "get_device_manager",
    "set_device_manager",
]
