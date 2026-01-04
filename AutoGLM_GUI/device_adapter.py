"""Device Protocol Adapter for phone_agent integration.

This module provides an adapter that bridges DeviceProtocol implementations
to the interface expected by phone_agent's DeviceFactory.

The adapter allows injecting any DeviceProtocol implementation (ADB, Mock, Remote)
into phone_agent without modifying the third-party code.

Example:
    >>> from AutoGLM_GUI.device_adapter import inject_device_protocol
    >>> from AutoGLM_GUI.devices import MockDevice, ADBDevice
    >>>
    >>> # For testing: inject mock device
    >>> mock = MockDevice("mock_001", state_machine)
    >>> inject_device_protocol(lambda _: mock)
    >>>
    >>> # For production: inject ADB device
    >>> devices = {"phone_1": ADBDevice("emulator-5554")}
    >>> inject_device_protocol(lambda device_id: devices[device_id])
"""

from typing import Callable

import phone_agent.device_factory as device_factory_module
from AutoGLM_GUI.device_protocol import DeviceProtocol, Screenshot


class DeviceProtocolAdapter:
    """
    Adapter that bridges DeviceProtocol to phone_agent's DeviceFactory interface.

    This adapter wraps a DeviceProtocol getter function and exposes the same
    interface as phone_agent's DeviceFactory, allowing seamless injection.

    The adapter handles:
    - Routing device operations to the correct DeviceProtocol instance
    - Converting between DeviceProtocol and DeviceFactory method signatures
    - Managing device_id parameters (phone_agent passes device_id to each method)
    """

    def __init__(
        self,
        get_device: Callable[[str | None], DeviceProtocol],
        default_device_id: str | None = None,
    ):
        """
        Initialize the adapter.

        Args:
            get_device: Function that returns a DeviceProtocol given a device_id.
                       If device_id is None, should return a default device.
            default_device_id: Default device ID to use when None is passed.
        """
        self._get_device = get_device
        self._default_device_id = default_device_id
        # For compatibility with code that checks device_type
        self.device_type = "protocol_adapter"

    def _device(self, device_id: str | None) -> DeviceProtocol:
        """Get device for the given ID."""
        effective_id = device_id or self._default_device_id
        return self._get_device(effective_id)

    # === Screenshot ===
    def get_screenshot(
        self, device_id: str | None = None, timeout: int = 10
    ) -> Screenshot:
        """Get screenshot from device."""
        return self._device(device_id).get_screenshot(timeout)

    # === Input Operations ===
    def tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ) -> None:
        """Tap at coordinates."""
        self._device(device_id).tap(x, y, delay)

    def double_tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ) -> None:
        """Double tap at coordinates."""
        self._device(device_id).double_tap(x, y, delay)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        device_id: str | None = None,
        delay: float | None = None,
    ) -> None:
        """Long press at coordinates."""
        self._device(device_id).long_press(x, y, duration_ms, delay)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        device_id: str | None = None,
        delay: float | None = None,
    ) -> None:
        """Swipe from start to end."""
        self._device(device_id).swipe(
            start_x, start_y, end_x, end_y, duration_ms, delay
        )

    def type_text(self, text: str, device_id: str | None = None) -> None:
        """Type text."""
        self._device(device_id).type_text(text)

    def clear_text(self, device_id: str | None = None) -> None:
        """Clear text."""
        self._device(device_id).clear_text()

    # === Navigation ===
    def back(self, device_id: str | None = None, delay: float | None = None) -> None:
        """Press back button."""
        self._device(device_id).back(delay)

    def home(self, device_id: str | None = None, delay: float | None = None) -> None:
        """Press home button."""
        self._device(device_id).home(delay)

    def launch_app(
        self, app_name: str, device_id: str | None = None, delay: float | None = None
    ) -> bool:
        """Launch an app."""
        return self._device(device_id).launch_app(app_name, delay)

    # === State Query ===
    def get_current_app(self, device_id: str | None = None) -> str:
        """Get current app name."""
        return self._device(device_id).get_current_app()

    # === Keyboard Management ===
    def detect_and_set_adb_keyboard(self, device_id: str | None = None) -> str:
        """Detect and set keyboard."""
        return self._device(device_id).detect_and_set_adb_keyboard()

    def restore_keyboard(self, ime: str, device_id: str | None = None) -> None:
        """Restore keyboard."""
        self._device(device_id).restore_keyboard(ime)

    # === Device Management ===
    def list_devices(self) -> list[str]:
        """
        List connected devices.

        Note: This is a simplified implementation. For full device listing,
        use ADBDeviceManager.list_devices() directly.
        """
        # This is called by some parts of phone_agent
        # Return the default device if available
        if self._default_device_id:
            return [self._default_device_id]
        return []

    def get_connection_class(self):
        """Not applicable for protocol adapter."""
        raise NotImplementedError(
            "Protocol adapter does not support get_connection_class. "
            "Use ADBDeviceManager for connection management."
        )


# Store original factory for restoration
_original_factory = None


def inject_device_protocol(
    get_device: Callable[[str | None], DeviceProtocol],
    default_device_id: str | None = None,
) -> DeviceProtocolAdapter:
    """
    Inject a DeviceProtocol implementation into phone_agent.

    This replaces phone_agent's global _device_factory with an adapter
    that routes all device operations through the provided DeviceProtocol.

    Args:
        get_device: Function that returns a DeviceProtocol given a device_id.
        default_device_id: Default device ID when None is passed.

    Returns:
        The adapter instance (for inspection or further configuration).

    Example:
        >>> # Single mock device
        >>> mock = MockDevice("mock_001", state_machine)
        >>> inject_device_protocol(lambda _: mock)
        >>>
        >>> # Multiple devices
        >>> devices = {
        ...     "phone_1": ADBDevice("emulator-5554"),
        ...     "phone_2": RemoteDevice("phone_2", "http://remote:8080"),
        ... }
        >>> inject_device_protocol(lambda did: devices.get(did, devices["phone_1"]))
    """
    # TODO： 不应该依赖这种全部变量
    global _original_factory

    # Save original factory if not already saved
    if _original_factory is None:
        _original_factory = device_factory_module._device_factory

    # Create and inject adapter
    adapter = DeviceProtocolAdapter(get_device, default_device_id)
    device_factory_module._device_factory = adapter

    return adapter


def restore_device_factory() -> None:
    """
    Restore the original device factory.

    Call this after testing to restore normal operation.
    """
    global _original_factory

    if _original_factory is not None:
        device_factory_module._device_factory = _original_factory
        _original_factory = None


class DeviceProtocolContext:
    """
    Context manager for temporarily injecting a DeviceProtocol.

    Example:
        >>> with DeviceProtocolContext(lambda _: mock_device):
        ...     agent.run("test instruction")
        >>> # Original factory is automatically restored
    """

    def __init__(
        self,
        get_device: Callable[[str | None], DeviceProtocol],
        default_device_id: str | None = None,
    ):
        """
        Initialize context.

        Args:
            get_device: Function that returns a DeviceProtocol given a device_id.
            default_device_id: Default device ID when None is passed.
        """
        self._get_device = get_device
        self._default_device_id = default_device_id
        self._original_factory = None

    def __enter__(self) -> DeviceProtocolAdapter:
        """Enter context and inject adapter."""
        self._original_factory = device_factory_module._device_factory
        return inject_device_protocol(self._get_device, self._default_device_id)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and restore original factory."""
        device_factory_module._device_factory = self._original_factory
        return None
