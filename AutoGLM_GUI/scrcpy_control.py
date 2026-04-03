"""Scrcpy Control Protocol - Control Android device via scrcpy socket.

This module implements the scrcpy control protocol for sending touch, key, text,
and other input events to an Android device through the scrcpy server's control channel.

Reference:
    - py-scrcpy-client: https://github.com/leng-yue/py-scrcpy-client
    - scrcpy develop doc: https://github.com/Genymobile/scrcpy/blob/master/doc/develop.md
"""

import struct
import socket

from AutoGLM_GUI.device_protocol import DeviceProtocol, Screenshot
from AutoGLM_GUI.trace import trace_span


# Scrcpy Control Message Types
class ControlMessageType:
    """Scrcpy control message type constants."""

    INJECT_TOUCH_EVENT = 0x01
    INJECT_KEYCODE = 0x02
    INJECT_TEXT = 0x03
    INJECT_SCROLL_EVENT = 0x04
    BACK_OR_SCREEN_ON = 0x05
    EXPAND_NOTIFICATION_PANEL = 0x06
    EXPAND_SETTINGS_PANEL = 0x07
    COLLAPSE_PANELS = 0x08
    GET_CLIPBOARD = 0x09
    SET_SCREEN_POWER_MODE = 0x0A
    SET_CLIPBOARD = 0x0B
    SET_SEND_SQUEEZE = 0x0C
    ROTATE_DEVICE = 0x0D


# Action constants for touch/key events
class Action:
    """Action constants for input events."""

    DOWN = 0x0000
    UP = 0x0001
    MOVE = 0x0002


# Android KeyEvent codes
class KeyCode:
    """Common Android keycodes."""

    HOME = 3
    BACK = 4
    CALL = 5
    ENDCALL = 6
    VOLUME_UP = 24
    VOLUME_DOWN = 25
    POWER = 26
    CAMERA = 27
    CLEAR = 28
    ENTER = 66
    DEL = 67
    FORWARD_DEL = 112
    TAB = 61
    ESCAPE = 111
    BACKSPACE = 112
    A = 29
    B = 30
    C = 31
    D = 32
    E = 33
    F = 34
    G = 35
    H = 36
    KEY_I = 37
    J = 38
    K = 39
    L = 40
    M = 41
    N = 42
    KEY_O = 43
    P = 44
    Q = 45
    R = 46
    S = 47
    T = 48
    U = 49
    V = 50
    W = 51
    X = 52
    Y = 53
    Z = 54


# Screen power modes
class ScreenPowerMode:
    """Screen power mode constants."""

    OFF = 0
    DOZE = 1
    NORMAL = 2
    DOZE_SUSPEND = 3
    SUSPEND = 4


class ScrcpyControlClient:
    """Scrcpy control client - sends control messages to scrcpy server."""

    def __init__(self, sock: socket.socket, device_width: int, device_height: int):
        """Initialize scrcpy control client.

        Args:
            sock: Connected socket to scrcpy server
            device_width: Device screen width
            device_height: Device screen height
        """
        self._sock = sock
        self._device_width = device_width
        self._device_height = device_height
        self._touch_id = 0x1234567887654321

    def _send_message(self, data: bytes) -> None:
        """Send raw message to scrcpy server.

        Args:
            data: Message data to send
        """
        self._sock.sendall(data)

    def _inject(self, msg_type: int, data: bytes) -> None:
        """Send inject message with type and data.

        Args:
            msg_type: Control message type
            data: Message payload
        """
        # Message format: [type: 1 byte][data: variable]
        message = bytes([msg_type]) + data
        self._send_message(message)

    # === Touch Events ===

    def touch_down(self, x: int, y: int, pressure: int = 0xFFFF) -> None:
        """Send touch down event.

        Args:
            x: X coordinate
            y: Y coordinate
            pressure: Touch pressure (default: 0xFFFF)
        """
        # Format: >BqiiHHHii
        # action(1) + touch_id(8) + x(4) + y(4) + w(2) + h(2) + pressure(2) + pointer_count(2) + pointer_id(2)
        data = struct.pack(
            ">BqiiHHHii",
            Action.DOWN,
            self._touch_id,
            x,
            y,
            self._device_width,
            self._device_height,
            pressure,
            1,
            1,
        )
        self._inject(ControlMessageType.INJECT_TOUCH_EVENT, data)

    def touch_up(self, x: int, y: int) -> None:
        """Send touch up event.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        data = struct.pack(
            ">BqiiHHHii",
            Action.UP,
            self._touch_id,
            x,
            y,
            self._device_width,
            self._device_height,
            0,  # No pressure on up
            1,
            1,
        )
        self._inject(ControlMessageType.INJECT_TOUCH_EVENT, data)

    def touch_move(self, x: int, y: int) -> None:
        """Send touch move event.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        data = struct.pack(
            ">BqiiHHHii",
            Action.MOVE,
            self._touch_id,
            x,
            y,
            self._device_width,
            self._device_height,
            0xFFFF,
            1,
            1,
        )
        self._inject(ControlMessageType.INJECT_TOUCH_EVENT, data)

    def tap(self, x: int, y: int) -> None:
        """Send tap (touch down + up) event.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        with trace_span("scrcpy.tap", attrs={"x": x, "y": y}):
            # Clamp coordinates
            x = max(0, min(x, self._device_width - 1))
            y = max(0, min(y, self._device_height - 1))

            self.touch_down(x, y)
            self.touch_up(x, y)

    def double_tap(self, x: int, y: int) -> None:
        """Send double tap event.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        with trace_span("scrcpy.double_tap", attrs={"x": x, "y": y}):
            self.tap(x, y)
            # Small delay between taps
            import time

            time.sleep(0.05)
            self.tap(x, y)

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> None:
        """Send long press event.

        Args:
            x: X coordinate
            y: Y coordinate
            duration_ms: Press duration in milliseconds
        """
        with trace_span(
            "scrcpy.long_press", attrs={"x": x, "y": y, "duration_ms": duration_ms}
        ):
            x = max(0, min(x, self._device_width - 1))
            y = max(0, min(y, self._device_height - 1))

            self.touch_down(x, y)

            # Hold for duration
            import time

            time.sleep(duration_ms / 1000.0)

            self.touch_up(x, y)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 300,
    ) -> None:
        """Send swipe gesture.

        Args:
            start_x: Start X coordinate
            start_y: Start Y coordinate
            end_x: End X coordinate
            end_y: End Y coordinate
            duration_ms: Swipe duration in milliseconds
        """
        with trace_span(
            "scrcpy.swipe",
            attrs={
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "duration_ms": duration_ms,
            },
        ):
            # Clamp coordinates
            start_x = max(0, min(start_x, self._device_width - 1))
            start_y = max(0, min(start_y, self._device_height - 1))
            end_x = max(0, min(end_x, self._device_width - 1))
            end_y = max(0, min(end_y, self._device_height - 1))

            # Send down event
            self.touch_down(start_x, start_y)

            # Send move events
            steps = max(1, duration_ms // 20)
            for i in range(1, steps):
                t = i / steps
                x = int(start_x + (end_x - start_x) * t)
                y = int(start_y + (end_y - start_y) * t)
                self.touch_move(x, y)

            # Send up event
            self.touch_up(end_x, end_y)

    # === Key Events ===

    def key_down(self, keycode: int, repeat: int = 0) -> None:
        """Send key down event.

        Args:
            keycode: Android keycode
            repeat: Repeat count
        """
        # Format: >Biii (action + keycode + repeat + meta)
        data = struct.pack(">Biii", Action.DOWN, keycode, repeat, 0)
        self._inject(ControlMessageType.INJECT_KEYCODE, data)

    def key_up(self, keycode: int) -> None:
        """Send key up event.

        Args:
            keycode: Android keycode
        """
        data = struct.pack(">Biii", Action.UP, keycode, 0, 0)
        self._inject(ControlMessageType.INJECT_KEYCODE, data)

    def keycode(self, keycode: int) -> None:
        """Send key press (down + up) event.

        Args:
            keycode: Android keycode
        """
        with trace_span("scrcpy.keycode", attrs={"keycode": keycode}):
            self.key_down(keycode)
            self.key_up(keycode)

    def back(self) -> None:
        """Press back button."""
        with trace_span("scrcpy.back"):
            self.keycode(KeyCode.BACK)

    def home(self) -> None:
        """Press home button."""
        with trace_span("scrcpy.home"):
            self.keycode(KeyCode.HOME)

    def power(self) -> None:
        """Press power button."""
        with trace_span("scrcpy.power"):
            self.keycode(KeyCode.POWER)

    def volume_up(self) -> None:
        """Press volume up button."""
        with trace_span("scrcpy.volume_up"):
            self.keycode(KeyCode.VOLUME_UP)

    def volume_down(self) -> None:
        """Press volume down button."""
        with trace_span("scrcpy.volume_down"):
            self.keycode(KeyCode.VOLUME_DOWN)

    def camera(self) -> None:
        """Press camera button."""
        with trace_span("scrcpy.camera"):
            self.keycode(KeyCode.CAMERA)

    def enter(self) -> None:
        """Press enter button."""
        with trace_span("scrcpy.enter"):
            self.keycode(KeyCode.ENTER)

    def backspace(self) -> None:
        """Press backspace button."""
        with trace_span("scrcpy.backspace"):
            self.keycode(KeyCode.BACKSPACE)

    def escape(self) -> None:
        """Press escape button."""
        with trace_span("scrcpy.escape"):
            self.keycode(KeyCode.ESCAPE)

    # === Text Input ===

    def type_text(self, text: str) -> None:
        """Send text input.

        Args:
            text: Text to type
        """
        with trace_span("scrcpy.type_text", attrs={"length": len(text)}):
            # Format: >i (length) + utf-8 bytes
            data = struct.pack(">i", len(text)) + text.encode("utf-8")
            self._inject(ControlMessageType.INJECT_TEXT, data)

    def clear_text(self) -> None:
        """Clear text (send backspace multiple times)."""
        with trace_span("scrcpy.clear_text"):
            # This is a simplified implementation
            # In practice, you might want to select all and delete
            for _ in range(20):
                self.backspace()

    # === Scroll Events ===

    def scroll(self, x: int, y: int, h: int, v: int) -> None:
        """Send scroll event.

        Args:
            x: X coordinate
            y: Y coordinate
            h: Horizontal movement
            v: Vertical movement
        """
        data = struct.pack(
            ">iiHHii",
            x,
            y,
            self._device_width,
            self._device_height,
            h,
            v,
        )
        self._inject(ControlMessageType.INJECT_SCROLL_EVENT, data)

    # === System Actions ===

    def back_or_turn_screen_on(self) -> None:
        """Press back or turn screen on."""
        with trace_span("scrcpy.back_or_turn_screen_on"):
            # Format: >B (action)
            data = struct.pack(">B", Action.DOWN)
            self._inject(ControlMessageType.BACK_OR_SCREEN_ON, data)

    def expand_notification_panel(self) -> None:
        """Expand notification panel."""
        with trace_span("scrcpy.expand_notification_panel"):
            self._inject(ControlMessageType.EXPAND_NOTIFICATION_PANEL, b"")

    def expand_settings_panel(self) -> None:
        """Expand settings panel."""
        with trace_span("scrcpy.expand_settings_panel"):
            self._inject(ControlMessageType.EXPAND_SETTINGS_PANEL, b"")

    def collapse_panels(self) -> None:
        """Collapse all panels."""
        with trace_span("scrcpy.collapse_panels"):
            self._inject(ControlMessageType.COLLAPSE_PANELS, b"")

    def set_screen_power_mode(self, mode: int = ScreenPowerMode.NORMAL) -> None:
        """Set screen power mode.

        Args:
            mode: Screen power mode (0=off, 2=normal)
        """
        data = struct.pack(">b", mode)
        self._inject(ControlMessageType.SET_SCREEN_POWER_MODE, data)

    def rotate_device(self) -> None:
        """Rotate device screen."""
        with trace_span("scrcpy.rotate_device"):
            self._inject(ControlMessageType.ROTATE_DEVICE, b"")

    # === Clipboard ===

    def set_clipboard(self, text: str, paste: bool = False) -> None:
        """Set clipboard text.

        Args:
            text: Text to copy
            paste: Whether to paste after setting
        """
        data = struct.pack(">?", paste) + text.encode("utf-8")
        self._inject(ControlMessageType.SET_CLIPBOARD, data)

    # === Properties ===

    @property
    def device_width(self) -> int:
        """Get device screen width."""
        return self._device_width

    @property
    def device_height(self) -> int:
        """Get device screen height."""
        return self._device_height


class ScrcpyDeviceProtocol(DeviceProtocol):
    """Scrcpy device implementation of DeviceProtocol.

    Uses scrcpy server's control channel to send input events to Android device.
    """

    def __init__(self, control_client: ScrcpyControlClient):
        """Initialize scrcpy device.

        Args:
            control_client: Scrcpy control client instance
        """
        self._control = control_client
        self._device_id = "scrcpy"

    @property
    def device_id(self) -> str:
        """Unique device identifier."""
        return self._device_id

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        """Capture current screen - not supported via scrcpy control.

        Raises:
            NotImplementedError: Screenshot should be obtained via ScrcpyStreamer
        """
        raise NotImplementedError(
            "Screenshot not supported via ScrcpyDeviceProtocol. "
            "Use ScrcpyStreamer for video streaming."
        )

    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Tap at specified coordinates."""
        with trace_span("device.tap", attrs={"x": x, "y": y, "impl": "scrcpy"}):
            self._control.tap(x, y)
            if delay:
                import time

                time.sleep(delay)

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Double tap at specified coordinates."""
        with trace_span("device.double_tap", attrs={"x": x, "y": y, "impl": "scrcpy"}):
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
            attrs={"x": x, "y": y, "duration_ms": duration_ms, "impl": "scrcpy"},
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
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "impl": "scrcpy",
            },
        ):
            self._control.swipe(start_x, start_y, end_x, end_y, duration_ms or 300)
            if delay:
                import time

                time.sleep(delay)

    def type_text(self, text: str) -> None:
        """Type text into the currently focused input field."""
        with trace_span(
            "device.type_text", attrs={"length": len(text), "impl": "scrcpy"}
        ):
            self._control.type_text(text)

    def clear_text(self) -> None:
        """Clear text in the currently focused input field."""
        with trace_span("device.clear_text", attrs={"impl": "scrcpy"}):
            self._control.clear_text()

    def back(self, delay: float | None = None) -> None:
        """Press the back button."""
        with trace_span("device.back", attrs={"impl": "scrcpy"}):
            self._control.back()
            if delay:
                import time

                time.sleep(delay)

    def home(self, delay: float | None = None) -> None:
        """Press the home button."""
        with trace_span("device.home", attrs={"impl": "scrcpy"}):
            self._control.home()
            if delay:
                import time

                time.sleep(delay)

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        """Launch an app by name - not directly supported via scrcpy.

        Returns:
            False: Launch app requires ADB or other method
        """
        # Note: App launch requires ADB command
        # This is a limitation of scrcpy control-only mode
        return False

    def get_current_app(self) -> str:
        """Get the currently focused app name - not supported via scrcpy.

        Returns:
            str: "Unknown" as scrcpy doesn't provide this info
        """
        return "Unknown"

    def detect_and_set_adb_keyboard(self) -> str:
        """Detect current keyboard and switch to ADB Keyboard if needed.

        Returns:
            str: Empty string (not supported via scrcpy)
        """
        return ""

    def restore_keyboard(self, ime: str) -> None:
        """Restore the original keyboard IME.

        Args:
            ime: The IME identifier to restore (ignored)
        """
        pass
