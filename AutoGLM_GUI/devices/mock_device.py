"""Mock Device implementation for testing.

This module provides a MockDevice that routes all operations through
a state machine, enabling controlled testing without real devices.
"""

from typing import TYPE_CHECKING

from AutoGLM_GUI.device_protocol import (
    DeviceInfo,
    DeviceManagerProtocol,
    DeviceProtocol,
    Screenshot,
)

if TYPE_CHECKING:
    from tests.integration.state_machine import StateMachine


class MockDevice(DeviceProtocol):
    """
    Mock device implementation driven by a state machine.

    All operations are routed through the state machine, which controls
    screenshots and validates actions (tap coordinates, etc.).

    Example:
        >>> from tests.integration.state_machine import load_test_case
        >>> state_machine, instruction, max_steps = load_test_case("scenario.yaml")
        >>>
        >>> device = MockDevice("mock_001", state_machine)
        >>> screenshot = device.get_screenshot()  # Returns current state's screenshot
        >>> device.tap(100, 200)  # State machine validates and transitions
    """

    def __init__(self, device_id: str, state_machine: "StateMachine"):
        """
        Initialize mock device.

        Args:
            device_id: Mock device ID.
            state_machine: State machine that controls test flow.
        """
        self._device_id = device_id
        self._state_machine = state_machine

    @property
    def device_id(self) -> str:
        """Unique device identifier."""
        return self._device_id

    @property
    def state_machine(self) -> "StateMachine":
        """Get the underlying state machine."""
        return self._state_machine

    # === Screenshot ===
    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        """Get screenshot from current state."""
        result = self._state_machine.get_current_screenshot()
        return Screenshot(
            base64_data=result.base64_data,
            width=result.width,
            height=result.height,
        )

    # === Input Operations ===
    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Handle tap action through state machine."""
        self._state_machine.handle_tap(x, y)

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Handle double tap (treated as single tap)."""
        self._state_machine.handle_tap(x, y)

    def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        """Handle long press (treated as tap for testing)."""
        self._state_machine.handle_tap(x, y)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        """Handle swipe action."""
        self._state_machine.handle_swipe(start_x, start_y, end_x, end_y)

    def type_text(self, text: str) -> None:
        """Handle text input (no-op in testing)."""
        pass

    def clear_text(self) -> None:
        """Handle text clear (no-op in testing)."""
        pass

    # === Navigation ===
    def back(self, delay: float | None = None) -> None:
        """Handle back button (no-op in testing)."""
        pass

    def home(self, delay: float | None = None) -> None:
        """Handle home button (no-op in testing)."""
        pass

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        """Handle app launch (always succeeds in testing)."""
        return True

    # === State Query ===
    def get_current_app(self) -> str:
        """Get current app name from the current state."""
        return self._state_machine.current_state.current_app

    # === Keyboard Management ===
    def detect_and_set_adb_keyboard(self) -> str:
        """Mock keyboard detection."""
        return "com.mock.keyboard"

    def restore_keyboard(self, ime: str) -> None:
        """Mock keyboard restore."""
        pass


class MockDeviceManager(DeviceManagerProtocol):
    """
    Mock device manager for testing.

    Provides a single mock device backed by a state machine.

    Example:
        >>> state_machine, _, _ = load_test_case("scenario.yaml")
        >>> manager = MockDeviceManager(state_machine)
        >>> device = manager.get_device("mock_001")
    """

    def __init__(
        self,
        state_machine: "StateMachine",
        device_id: str = "mock_device_001",
    ):
        """
        Initialize mock device manager.

        Args:
            state_machine: State machine for the mock device.
            device_id: ID for the mock device.
        """
        self._device_id = device_id
        self._device = MockDevice(device_id, state_machine)

    def list_devices(self) -> list[DeviceInfo]:
        """List the mock device."""
        return [
            DeviceInfo(
                device_id=self._device_id,
                status="online",
                model="MockPhone",
                platform="android",
                connection_type="mock",
            )
        ]

    def get_device(self, device_id: str) -> MockDevice:
        """Get the mock device."""
        if device_id != self._device_id:
            raise KeyError(f"Device '{device_id}' not found")
        return self._device

    def connect(self, address: str, timeout: int = 10) -> tuple[bool, str]:
        """Mock connect (always succeeds)."""
        return True, f"Connected to {address}"

    def disconnect(self, device_id: str) -> tuple[bool, str]:
        """Mock disconnect (always succeeds)."""
        return True, f"Disconnected from {device_id}"


# Verify MockDeviceManager implements DeviceManagerProtocol
# Same issue as above - can't verify at import time
