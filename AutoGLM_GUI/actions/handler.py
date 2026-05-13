"""Action handler for executing phone operations."""

from typing import Any
from collections.abc import Callable

from AutoGLM_GUI.adb.timing import TIMING_CONFIG
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.trace import trace_sleep, trace_span

from .types import ActionResult


class ActionHandler:
    def __init__(
        self,
        device: DeviceProtocol,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.device = device
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover

    def execute(
        self, action: dict[str, Any], screen_width: int, screen_height: int
    ) -> ActionResult:
        action_type = action.get("_metadata")
        action_name = action.get("action")
        with trace_span(
            "action.execute",
            attrs={
                "action_type": action_type,
                "action_name": action_name,
                "screen_width": screen_width,
                "screen_height": screen_height,
            },
        ) as span:
            if action_type == "finish":
                result = ActionResult(
                    success=True, should_finish=True, message=action.get("message")
                )
                span.set_attributes(
                    {
                        "success": result.success,
                        "should_finish": result.should_finish,
                    }
                )
                return result

            if action_type != "do":
                result = ActionResult(
                    success=False,
                    should_finish=True,
                    message=f"Unknown action type: {action_type}",
                )
                span.set_attributes(
                    {
                        "success": result.success,
                        "should_finish": result.should_finish,
                    }
                )
                return result

            if not isinstance(action_name, str) or not action_name:
                result = ActionResult(
                    success=False,
                    should_finish=False,
                    message=f"Unknown action: {action_name}",
                )
                span.set_attributes(
                    {
                        "success": result.success,
                        "should_finish": result.should_finish,
                    }
                )
                return result

            handler_method = self._get_handler(action_name)

            if handler_method is None:
                result = ActionResult(
                    success=False,
                    should_finish=False,
                    message=f"Unknown action: {action_name}",
                )
                span.set_attributes(
                    {
                        "success": result.success,
                        "should_finish": result.should_finish,
                    }
                )
                return result

            try:
                result = handler_method(action, screen_width, screen_height)
                span.set_attributes(
                    {
                        "success": result.success,
                        "should_finish": result.should_finish,
                    }
                )
                return result
            except Exception as e:
                result = ActionResult(
                    success=False, should_finish=False, message=f"Action failed: {e}"
                )
                span.set_attributes(
                    {
                        "success": result.success,
                        "should_finish": result.should_finish,
                    }
                )
                return result

    def _get_handler(
        self, action_name: str
    ) -> Callable[[dict[str, Any], int, int], ActionResult] | None:
        handlers = {
            "Launch": self._handle_launch,
            "Tap": self._handle_tap,
            "Type": self._handle_type,
            "Type_Name": self._handle_type,
            "Swipe": self._handle_swipe,
            "Back": self._handle_back,
            "Home": self._handle_home,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
            "Interact": self._handle_interact,
        }
        return handlers.get(action_name)

    def _convert_relative_to_absolute(
        self, element: list[int], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        clamped_x = max(0, min(element[0], 1000))
        clamped_y = max(0, min(element[1], 1000))
        x = int(clamped_x / 1000 * screen_width)
        y = int(clamped_y / 1000 * screen_height)
        return x, y

    def _handle_launch(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        app_name = action.get("app")
        if not app_name:
            return ActionResult(False, False, "No app name specified")

        success = self.device.launch_app(app_name)
        if success:
            return ActionResult(True, False)
        return ActionResult(False, False, f"App not found: {app_name}")

    def _handle_tap(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)

        if "message" in action:
            if not self.confirmation_callback(action["message"]):
                return ActionResult(
                    success=False,
                    should_finish=True,
                    message="User cancelled sensitive operation",
                )

        self.device.tap(x, y)
        return ActionResult(True, False)

    _ADB_IME = "com.android.adbkeyboard/.AdbIME"

    def _handle_type(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        text = action.get("text", "")

        original_ime = self.device.detect_and_set_adb_keyboard()
        need_restore = self._ADB_IME not in original_ime

        if need_restore:
            trace_sleep(
                TIMING_CONFIG.action.keyboard_switch_delay,
                name="sleep.keyboard_switch",
                attrs={"action_name": "Type"},
            )

        self.device.clear_text()
        trace_sleep(
            TIMING_CONFIG.action.text_clear_delay,
            name="sleep.text_clear_delay",
            attrs={"action_name": "Type"},
        )

        self.device.type_text(text)
        trace_sleep(
            TIMING_CONFIG.action.text_input_delay,
            name="sleep.text_input_delay",
            attrs={"action_name": "Type", "text_length": len(text)},
        )

        if need_restore:
            self.device.restore_keyboard(original_ime)
            trace_sleep(
                TIMING_CONFIG.action.keyboard_restore_delay,
                name="sleep.keyboard_restore_delay",
                attrs={"action_name": "Type"},
            )

        return ActionResult(True, False)

    def _handle_swipe(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        start = action.get("start")
        end = action.get("end")

        if not start or not end:
            return ActionResult(False, False, "Missing swipe coordinates")

        start_x, start_y = self._convert_relative_to_absolute(start, width, height)
        end_x, end_y = self._convert_relative_to_absolute(end, width, height)

        self.device.swipe(start_x, start_y, end_x, end_y)
        return ActionResult(True, False)

    def _handle_back(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        self.device.back()
        return ActionResult(True, False)

    def _handle_home(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        self.device.home()
        return ActionResult(True, False)

    def _handle_double_tap(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        self.device.double_tap(x, y)
        return ActionResult(True, False)

    def _handle_long_press(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        self.device.long_press(x, y)
        return ActionResult(True, False)

    MAX_WAIT_SECONDS = 30

    def _handle_wait(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        duration_str = action.get("duration", "1 seconds")
        try:
            duration = float(duration_str.replace("seconds", "").strip())
        except ValueError:
            duration = 1.0

        duration = min(duration, self.MAX_WAIT_SECONDS)
        trace_sleep(
            duration,
            name="sleep.wait_action",
            attrs={"action_name": "Wait"},
        )
        return ActionResult(True, False)

    def _handle_takeover(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        message = action.get("message", "User intervention required")
        self.takeover_callback(message)
        return ActionResult(True, False)

    def _handle_note(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        return ActionResult(True, False)

    def _handle_call_api(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        """Handle API call action (placeholder for summarization)."""
        # This action is typically used for content summarization
        # Implementation depends on specific requirements
        return ActionResult(True, False)

    def _handle_interact(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        """Handle interaction request (user choice needed)."""
        # This action signals that user input is needed
        return ActionResult(True, False, message="User interaction required")

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        response = input(f"\n⚠️  Confirm action: {message} (y/n): ")
        return response.lower() in ("y", "yes")

    @staticmethod
    def _default_takeover(message: str) -> None:
        input(f"\n🤚 {message}. Press Enter to continue...")
