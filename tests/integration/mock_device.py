"""Mock device factory for integration testing.

This module provides a MockDeviceFactory that replaces the real device
interaction with state machine controlled responses.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.integration.state_machine import StateMachine, ScreenshotResult


class MockDeviceFactory:
    """
    Mock implementation of DeviceFactory for testing.

    All device operations are routed through the state machine,
    allowing controlled test scenarios without a real device.
    """

    def __init__(self, state_machine: "StateMachine"):
        """
        Initialize the mock device factory.

        Args:
            state_machine: The state machine controlling test flow
        """
        self.state_machine = state_machine
        self.device_type = "mock"  # For compatibility

    def get_screenshot(
        self, device_id: str | None = None, timeout: int = 10
    ) -> "ScreenshotResult":
        """Get screenshot from current state."""
        return self.state_machine.get_current_screenshot()

    def get_current_app(self, device_id: str | None = None) -> str:
        """Get current app name from the current state."""
        return self.state_machine.current_state.current_app

    def tap(
        self,
        x: int,
        y: int,
        device_id: str | None = None,
        delay: float | None = None,
    ) -> None:
        """Handle tap action through state machine."""
        self.state_machine.handle_tap(x, y)

    def double_tap(
        self,
        x: int,
        y: int,
        device_id: str | None = None,
        delay: float | None = None,
    ) -> None:
        """Handle double tap (treated as single tap)."""
        self.state_machine.handle_tap(x, y)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        device_id: str | None = None,
        delay: float | None = None,
    ) -> None:
        """Handle long press (treated as tap for testing)."""
        self.state_machine.handle_tap(x, y)

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
        """Handle swipe action."""
        self.state_machine.handle_swipe(start_x, start_y, end_x, end_y)

    def back(self, device_id: str | None = None, delay: float | None = None) -> None:
        """Handle back button (no-op in testing)."""
        pass

    def home(self, device_id: str | None = None, delay: float | None = None) -> None:
        """Handle home button (no-op in testing)."""
        pass

    def launch_app(
        self,
        app_name: str,
        device_id: str | None = None,
        delay: float | None = None,
    ) -> bool:
        """Handle app launch (always succeeds in testing)."""
        return True

    def type_text(self, text: str, device_id: str | None = None) -> None:
        """Handle text input (no-op in testing)."""
        pass

    def clear_text(self, device_id: str | None = None) -> None:
        """Handle text clear (no-op in testing)."""
        pass

    def detect_and_set_adb_keyboard(self, device_id: str | None = None) -> str:
        """Mock keyboard detection."""
        return "com.mock.keyboard"

    def restore_keyboard(self, ime: str, device_id: str | None = None) -> None:
        """Mock keyboard restore."""
        pass

    def list_devices(self) -> list[str]:
        """Return mock device list."""
        return ["mock_device_001"]

    def get_connection_class(self):
        """Not applicable for mock."""
        raise NotImplementedError("Mock device does not support connection class")
