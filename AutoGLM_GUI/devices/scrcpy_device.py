"""Scrcpy Device implementation of DeviceProtocol.

This module provides a DeviceProtocol implementation that uses scrcpy's
control channel to send input events to Android devices.

Example:
    >>> from AutoGLM_GUI.devices import ScrcpyDevice
    >>> from AutoGLM_GUI.scrcpy_control import ScrcpyControlClient
    >>>
    >>> # When scrcpy stream is already running
    >>> device = ScrcpyDevice("device_001", control_client)
    >>> device.tap(100, 200)
    >>> device.swipe(100, 200, 300, 400)
"""

from AutoGLM_GUI.device_protocol import DeviceProtocol, Screenshot
from AutoGLM_GUI.scrcpy_control import ScrcpyControlClient
from AutoGLM_GUI.trace import trace_span


class ScrcpyDevice(DeviceProtocol):
    """
    Scrcpy device implementation using scrcpy control channel.

    This device uses the scrcpy server's control channel (via ScrcpyControlClient)
    to send input events directly through the socket connection, providing
    lower latency than traditional ADB commands.

    Note: Screenshot is not supported through scrcpy control - use ADB for screenshots.
    """

    def __init__(self, device_id: str, control_client: ScrcpyControlClient):
        """Initialize scrcpy device.

        Args:
            device_id: Device identifier
            control_client: Scrcpy control client instance
        """
        self._device_id = device_id
        self._control = control_client

    @property
    def device_id(self) -> str:
        """Unique device identifier."""
        return self._device_id

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        """Capture current screen - NOT SUPPORTED via scrcpy.

        Screenshot should be obtained via scrcpy video stream or ADB.
        This method raises NotImplementedError.

        Raises:
            NotImplementedError: Screenshot not supported via scrcpy control
        """
        raise NotImplementedError(
            "Screenshot not supported via ScrcpyDevice. "
            "Use scrcpy video stream or ADB for screenshots."
        )

    # === Input Operations ===

    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Tap at specified coordinates."""
        with trace_span(
            "device.tap",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "x": x,
                "y": y,
            },
        ):
            self._control.tap(x, y)
            if delay:
                import time

                time.sleep(delay)

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Double tap at specified coordinates."""
        with trace_span(
            "device.double_tap",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "x": x,
                "y": y,
            },
        ):
            self._control.double_tap(x, y)
            if delay:
                import time

                time.sleep(delay)

    def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        """Long press at specified coordinates."""
        with trace_span(
            "device.long_press",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "x": x,
                "y": y,
                "duration_ms": duration_ms,
            },
        ):
            self._control.long_press(x, y, duration_ms)
            if delay:
                import time

                time.sleep(delay)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        """Swipe from start to end coordinates."""
        with trace_span(
            "device.swipe",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
            },
        ):
            self._control.swipe(start_x, start_y, end_x, end_y, duration_ms or 300)
            if delay:
                import time

                time.sleep(delay)

    # === Touch Events (Drag) ===

    def touch_down(self, x: int, y: int, pressure: int = 0xFFFF) -> None:
        """Send touch DOWN event at specified coordinates."""
        with trace_span(
            "device.touch_down",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "x": x,
                "y": y,
            },
        ):
            self._control.touch_down(x, y, pressure)

    def touch_move(self, x: int, y: int) -> None:
        """Send touch MOVE event to specified coordinates."""
        with trace_span(
            "device.touch_move",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "x": x,
                "y": y,
            },
        ):
            self._control.touch_move(x, y)

    def touch_up(self, x: int, y: int) -> None:
        """Send touch UP event at specified coordinates."""
        with trace_span(
            "device.touch_up",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "x": x,
                "y": y,
            },
        ):
            self._control.touch_up(x, y)

    # === Text Input ===

    def type_text(self, text: str) -> None:
        """Type text into the currently focused input field."""
        with trace_span(
            "device.type_text",
            attrs={
                "device_id": self._device_id,
                "device_impl": "scrcpy",
                "length": len(text),
            },
        ):
            self._control.type_text(text)

    def clear_text(self) -> None:
        """Clear text in the currently focused input field."""
        with trace_span(
            "device.clear_text",
            attrs={"device_id": self._device_id, "device_impl": "scrcpy"},
        ):
            self._control.clear_text()

    # === Navigation ===

    def back(self, delay: float | None = None) -> None:
        """Press the back button."""
        with trace_span(
            "device.back", attrs={"device_id": self._device_id, "device_impl": "scrcpy"}
        ):
            self._control.back()
            if delay:
                import time

                time.sleep(delay)

    def home(self, delay: float | None = None) -> None:
        """Press the home button."""
        with trace_span(
            "device.home", attrs={"device_id": self._device_id, "device_impl": "scrcpy"}
        ):
            self._control.home()
            if delay:
                import time

                time.sleep(delay)

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        """Launch an app by name.

        Note: App launch requires ADB command, not supported via scrcpy control.

        Args:
            app_name: The app name to launch
            delay: Optional delay after launching in seconds

        Returns:
            bool: False (app launch not supported via scrcpy)
        """
        return False

    # === State Query ===

    def get_current_app(self) -> str:
        """Get the currently focused app name.

        Note: Not supported via scrcpy control channel.

        Returns:
            str: "Unknown"
        """
        return "Unknown"

    # === Keyboard Management ===

    def detect_and_set_adb_keyboard(self) -> str:
        """Detect current keyboard and switch to ADB Keyboard if needed.

        Note: Not supported via scrcpy control.

        Returns:
            str: Empty string
        """
        return ""

    def restore_keyboard(self, ime: str) -> None:
        """Restore the original keyboard IME.

        Note: Not supported via scrcpy control.

        Args:
            ime: The IME identifier to restore (ignored)
        """
        pass


class ScrcpyDeviceManager:
    """Manager for scrcpy devices."""

    def __init__(self):
        """Initialize scrcpy device manager."""
        self._devices: dict[str, ScrcpyDevice] = {}

    def add_device(
        self, device_id: str, control_client: ScrcpyControlClient
    ) -> ScrcpyDevice:
        """Add a scrcpy device.

        Args:
            device_id: Device identifier
            control_client: Scrcpy control client

        Returns:
            ScrcpyDevice: The created device
        """
        device = ScrcpyDevice(device_id, control_client)
        self._devices[device_id] = device
        return device

    def get_device(self, device_id: str) -> ScrcpyDevice | None:
        """Get a scrcpy device by ID.

        Args:
            device_id: Device identifier

        Returns:
            ScrcpyDevice | None: Device if found
        """
        return self._devices.get(device_id)

    def remove_device(self, device_id: str) -> bool:
        """Remove a scrcpy device.

        Args:
            device_id: Device identifier

        Returns:
            bool: True if removed
        """
        if device_id in self._devices:
            del self._devices[device_id]
            return True
        return False

    def list_devices(self) -> list[str]:
        """List all device IDs.

        Returns:
            list[str]: List of device IDs
        """
        return list(self._devices.keys())
