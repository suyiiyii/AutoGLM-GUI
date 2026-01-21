"""Device Protocol - Abstract interface for device operations.

This module defines the protocol (interface) that all device implementations
must follow. The actual implementation can be:
- ADB (local subprocess calls)
- Accessibility Service
- Remote HTTP/gRPC calls
- Mock (for testing)

Example:
    >>> from AutoGLM_GUI.devices import ADBDevice, MockDevice
    >>>
    >>> # Production: use ADB
    >>> device = ADBDevice("emulator-5554")
    >>> screenshot = device.get_screenshot()
    >>> device.tap(100, 200)
    >>>
    >>> # Testing: use Mock with state machine
    >>> mock = MockDevice("mock_001", state_machine)
    >>> screenshot = mock.get_screenshot()  # Returns state machine's screenshot
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class Screenshot:
    """Screenshot result from device."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False


@dataclass
class DeviceInfo:
    """Information about a connected device."""

    device_id: str
    status: str  # "online" | "offline" | "unauthorized"
    model: str | None = None
    platform: str = "android"  # "android" | "ios" | "harmonyos"
    connection_type: str = "usb"  # "usb" | "wifi" (ADB WiFi) | "remote" (HTTP Remote)


@runtime_checkable
class DeviceProtocol(Protocol):
    """
    Device operation protocol - all device implementations must follow this interface.

    This protocol abstracts device operations, allowing the control logic to be
    independent of the actual device implementation (ADB, Accessibility, Remote, etc.).

    The concrete implementation decides HOW to perform operations:
    - ADBDevice: Uses `adb shell input tap` commands
    - AccessibilityDevice: Uses Android Accessibility Service
    - RemoteDevice: Sends HTTP/gRPC requests to a remote agent
    - MockDevice: Routes operations through a state machine for testing
    """

    @property
    def device_id(self) -> str:
        """Unique device identifier."""
        ...

    # === Screenshot ===
    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        """
        Capture current screen.

        Args:
            timeout: Timeout in seconds for the operation.

        Returns:
            Screenshot object containing base64 data and dimensions.
        """
        ...

    # === Input Operations ===
    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        """
        Tap at specified coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
            delay: Optional delay after tap in seconds.
        """
        ...

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        """
        Double tap at specified coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
            delay: Optional delay after double tap in seconds.
        """
        ...

    def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        """
        Long press at specified coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
            duration_ms: Duration of press in milliseconds.
            delay: Optional delay after long press in seconds.
        """
        ...

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        """
        Swipe from start to end coordinates.

        Args:
            start_x: Starting X coordinate.
            start_y: Starting Y coordinate.
            end_x: Ending X coordinate.
            end_y: Ending Y coordinate.
            duration_ms: Duration of swipe in milliseconds.
            delay: Optional delay after swipe in seconds.
        """
        ...

    def type_text(self, text: str) -> None:
        """
        Type text into the currently focused input field.

        Args:
            text: The text to type.
        """
        ...

    def clear_text(self) -> None:
        """Clear text in the currently focused input field."""
        ...

    # === Navigation ===
    def back(self, delay: float | None = None) -> None:
        """
        Press the back button.

        Args:
            delay: Optional delay after pressing back in seconds.
        """
        ...

    def home(self, delay: float | None = None) -> None:
        """
        Press the home button.

        Args:
            delay: Optional delay after pressing home in seconds.
        """
        ...

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        """
        Launch an app by name.

        Args:
            app_name: The app name to launch.
            delay: Optional delay after launching in seconds.

        Returns:
            True if app was launched successfully, False otherwise.
        """
        ...

    # === State Query ===
    def get_current_app(self) -> str:
        """
        Get the currently focused app name.

        Returns:
            The app name if recognized, otherwise "System Home".
        """
        ...

    # === Keyboard Management ===
    def detect_and_set_adb_keyboard(self) -> str:
        """
        Detect current keyboard and switch to ADB Keyboard if needed.

        Returns:
            The original keyboard IME identifier for later restoration.
        """
        ...

    def restore_keyboard(self, ime: str) -> None:
        """
        Restore the original keyboard IME.

        Args:
            ime: The IME identifier to restore.
        """
        ...


@runtime_checkable
class DeviceManagerProtocol(Protocol):
    """Device manager protocol - manages multiple devices."""

    def list_devices(self) -> list[DeviceInfo]:
        """
        List all available devices.

        Returns:
            List of DeviceInfo objects.
        """
        ...

    def get_device(self, device_id: str) -> DeviceProtocol:
        """
        Get a device instance by ID.

        Args:
            device_id: The device ID.

        Returns:
            DeviceProtocol implementation for the device.

        Raises:
            KeyError: If device not found.
        """
        ...

    def connect(self, address: str, timeout: int = 10) -> tuple[bool, str]:
        """
        Connect to a remote device.

        Args:
            address: Device address (e.g., "192.168.1.100:5555").
            timeout: Connection timeout in seconds.

        Returns:
            Tuple of (success, message).
        """
        ...

    def disconnect(self, device_id: str) -> tuple[bool, str]:
        """
        Disconnect from a device.

        Args:
            device_id: The device ID to disconnect.

        Returns:
            Tuple of (success, message).
        """
        ...
