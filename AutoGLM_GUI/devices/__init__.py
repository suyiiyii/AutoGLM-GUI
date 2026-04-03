"""Device implementations for the DeviceProtocol interface.

This package provides concrete implementations of DeviceProtocol:
- ADBDevice: Local ADB subprocess calls
- MockDevice: State machine driven mock for testing
- RemoteDevice: HTTP client for remote device agents
- ScrcpyDevice: Scrcpy control channel for low-latency input

Example:
    >>> from AutoGLM_GUI.devices import ADBDevice, RemoteDevice
    >>>
    >>> # Local ADB device
    >>> device = ADBDevice("emulator-5554")
    >>> device.tap(100, 200)
    >>>
    >>> # Remote device via HTTP
    >>> remote = RemoteDevice("phone_001", "http://device-agent:8001")
    >>> remote.tap(100, 200)
    >>>
    >>> # Scrcpy device (when scrcpy stream is running)
    >>> from AutoGLM_GUI.devices import ScrcpyDevice
    >>> scrcpy_dev = ScrcpyDevice("device_001", control_client)
    >>> scrcpy_dev.tap(100, 200)
"""

from AutoGLM_GUI.devices.adb_device import ADBDevice, ADBDeviceManager
from AutoGLM_GUI.devices.mock_device import MockDevice
from AutoGLM_GUI.devices.remote_device import RemoteDevice, RemoteDeviceManager
from AutoGLM_GUI.devices.scrcpy_device import ScrcpyDevice, ScrcpyDeviceManager

__all__ = [
    "ADBDevice",
    "ADBDeviceManager",
    "MockDevice",
    "RemoteDevice",
    "RemoteDeviceManager",
    "ScrcpyDevice",
    "ScrcpyDeviceManager",
]
