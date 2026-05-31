"""Test Take_over / Interact action handling and user interaction flow."""

from typing import Any
from AutoGLM_GUI.actions import ActionHandler


class FakeDevice:
    """Minimal fake device for action handler tests."""

    @property
    def device_id(self) -> str:
        return "fake-device"

    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        _ = delay

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        _ = (duration_ms, delay)

    def type_text(self, text: str) -> None: ...

    def back(self, delay: float | None = None) -> None:
        _ = delay

    def home(self, delay: float | None = None) -> None:
        _ = delay

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        _ = delay

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        delay: float | None = None,
    ) -> None:
        _ = (duration_ms, delay)

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        _ = delay
        return True

    def get_screenshot(self, timeout: int = 10) -> Any:
        return None

    def get_current_app(self) -> str:
        return "TestApp"

    def detect_and_set_adb_keyboard(self) -> str:
        return ""

    def restore_keyboard(self, ime: str) -> None: ...

    def clear_text(self) -> None: ...


def _noop_takeover(message: str) -> None:
    pass


class TestTakeoverAction:
    """Test Take_over action handler behavior."""

    def test_takeover_success_and_should_not_finish(self) -> None:
        device = FakeDevice()
        handler = ActionHandler(device, takeover_callback=_noop_takeover)

        result = handler.execute(
            {"_metadata": "do", "action": "Take_over", "message": "请登录后继续"},
            100,
            200,
        )

        assert result.success is True
        assert result.should_finish is False
        assert result.message == "TAKEOVER_REQUIRED:\n 请登录后继续"

    def test_takeover_default_message(self) -> None:
        device = FakeDevice()
        handler = ActionHandler(device, takeover_callback=_noop_takeover)

        result = handler.execute(
            {"_metadata": "do", "action": "Take_over"},
            100,
            200,
        )

        assert result.success is True
        assert result.message == ("TAKEOVER_REQUIRED:\n User intervention required")

    def test_takeover_callback_receives_raw_message(self) -> None:
        device = FakeDevice()
        takeovers: list[str] = []

        handler = ActionHandler(
            device, takeover_callback=lambda msg: takeovers.append(msg)
        )

        result = handler.execute(
            {"_metadata": "do", "action": "Take_over", "message": "login"},
            100,
            200,
        )

        assert result.success is True
        assert takeovers == ["login"]


class TestInteractAction:
    """Test Interact action handler behavior."""

    def test_interact_success_and_should_not_finish(self) -> None:
        device = FakeDevice()
        handler = ActionHandler(device)

        result = handler.execute(
            {"_metadata": "do", "action": "Interact"},
            100,
            200,
        )

        assert result.success is True
        assert result.should_finish is False
        assert result.message == "INTERACT_REQUIRED: User interaction required"


class TestInteractionActionsIntegration:
    """Test the full interaction flow covering agent-executor handoff.

    These tests verify the contract between the backend ActionHandler,
    the agent stream loop (takeover event yielding), and frontend detection.
    """

    def test_takeover_message_format_for_frontend_detection(self) -> None:
        """Frontend detects takeover by content prefix."""
        device = FakeDevice()
        handler = ActionHandler(device, takeover_callback=_noop_takeover)

        result = handler.execute(
            {"_metadata": "do", "action": "Take_over", "message": "请操作"},
            100,
            200,
        )

        assert result.message is not None
        assert result.message.startswith("TAKEOVER_REQUIRED:")

    def test_interact_message_format_for_frontend_detection(self) -> None:
        """Frontend detects interact by content prefix."""
        device = FakeDevice()
        handler = ActionHandler(device)

        result = handler.execute(
            {"_metadata": "do", "action": "Interact"},
            100,
            200,
        )

        assert result.message is not None
        assert result.message.startswith("INTERACT_REQUIRED:")

    def test_multiline_takeover_message(self) -> None:
        """Take_over message with multiline content should keep format."""
        device = FakeDevice()
        handler = ActionHandler(device, takeover_callback=_noop_takeover)

        message = "请选择登录方式：\n1. 手机号\n2. 邮箱"
        result = handler.execute(
            {"_metadata": "do", "action": "Take_over", "message": message},
            100,
            200,
        )

        assert result.message is not None
        assert message in result.message
        assert result.message.startswith("TAKEOVER_REQUIRED:")

    def test_takeover_as_part_of_step_flow(self) -> None:
        """Normal actions before and after Take_over should work correctly."""
        device = FakeDevice()
        handler = ActionHandler(device, takeover_callback=_noop_takeover)

        launch = handler.execute(
            {"_metadata": "do", "action": "Launch", "app": "飞书"}, 100, 200
        )
        assert launch.success is True
        assert launch.should_finish is False

        takeover = handler.execute(
            {"_metadata": "do", "action": "Take_over", "message": "登录"},
            100,
            200,
        )
        assert takeover.success is True
        assert takeover.should_finish is False

        back = handler.execute({"_metadata": "do", "action": "Back"}, 100, 200)
        assert back.success is True
        assert back.should_finish is False

    def test_takeover_preserves_should_not_finish(self) -> None:
        """Take_over/Interact must never set should_finish=True so
        the agent stream loop yields a takeover event instead of stopping."""
        device = FakeDevice()
        handler = ActionHandler(device, takeover_callback=_noop_takeover)

        for action_dict in (
            {"_metadata": "do", "action": "Take_over", "message": "x"},
            {"_metadata": "do", "action": "Interact"},
        ):
            result = handler.execute(action_dict, 100, 200)
            assert result.success is True, f"Expected success for {action_dict}"
            assert result.should_finish is False, (
                f"should_finish must be False for {action_dict}"
            )
