"""Test Take_over / Interact action handling and user interaction flow."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from AutoGLM_GUI.actions import ActionHandler
from AutoGLM_GUI.agents.base import AsyncAgentBase
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.model import MessageBuilder


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


class FakeScreenshot:
    base64_data = "fake-screen"


class StreamFakeDevice(FakeDevice):
    def __init__(self) -> None:
        self.screenshot_calls = 0
        self.current_app_calls = 0

    def get_screenshot(self, timeout: int = 10) -> Any:
        _ = timeout
        self.screenshot_calls += 1
        return FakeScreenshot()

    def get_current_app(self) -> str:
        self.current_app_calls += 1
        return "TestApp"


class FakeInteractionAgent(AsyncAgentBase):
    def __init__(self, device: StreamFakeDevice) -> None:
        self.prepared_tasks: list[str] = []
        super().__init__(
            model_config=ModelConfig(),
            agent_config=AgentConfig(max_steps=5, verbose=False),
            device=device,
            takeover_callback=_noop_takeover,
        )

    def _get_default_system_prompt(self, lang: str) -> str:
        _ = lang
        return "system"

    def _prepare_initial_context(
        self,
        task: str,
        screenshot_base64: str,
        current_app: str,
        reference_images: list[dict[str, str]] | None = None,
    ) -> None:
        _ = reference_images
        self.prepared_tasks.append(task)
        self._context.append(
            MessageBuilder.create_user_message(
                f"{task}|{screenshot_base64}|{current_app}"
            )
        )

    async def _execute_step(self) -> AsyncGenerator[dict[str, Any], None]:
        self._step_count += 1
        if self._step_count == 1:
            yield {
                "type": "step",
                "data": {
                    "step": self._step_count,
                    "thinking": "need user",
                    "action": {"action": "Take_over", "message": "登录后继续"},
                    "success": True,
                    "finished": False,
                    "waiting_for_input": True,
                    "message": "TAKEOVER_REQUIRED:\n 登录后继续",
                },
            }
            return

        yield {
            "type": "step",
            "data": {
                "step": self._step_count,
                "thinking": "continued",
                "action": {"action": "Tap"},
                "success": True,
                "finished": True,
                "message": "done",
            },
        }


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
    """Test interaction contracts across backend layers."""

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

    def test_agent_stream_yields_takeover_and_continues_without_reset(self) -> None:
        """Agent stream must pause on interaction and preserve state on continue."""
        device = StreamFakeDevice()
        agent = FakeInteractionAgent(device)

        first_events = asyncio.run(_collect_stream(agent.stream("打开飞书")))

        assert [event["type"] for event in first_events] == ["step", "takeover"]
        assert first_events[0]["data"]["waiting_for_input"] is True
        assert first_events[1]["data"] == {
            "message": "TAKEOVER_REQUIRED:\n 登录后继续",
            "steps": 1,
            "success": True,
            "stop_reason": "takeover",
        }
        assert agent.step_count == 1
        assert agent.prepared_tasks == ["打开飞书"]
        assert device.screenshot_calls == 1
        assert device.current_app_calls == 1

        second_events = asyncio.run(
            _collect_stream(agent.stream("继续", continue_with="已完成登录"))
        )

        assert [event["type"] for event in second_events] == ["step", "done"]
        assert second_events[0]["data"]["step"] == 2
        assert second_events[1]["data"] == {
            "message": "done",
            "steps": 2,
            "success": True,
        }
        assert agent.step_count == 2
        assert agent.prepared_tasks == ["打开飞书"]
        assert device.screenshot_calls == 1
        assert device.current_app_calls == 1
        assert agent.context[-1] == MessageBuilder.create_user_message("已完成登录")


async def _collect_stream(stream: Any) -> list[dict[str, Any]]:
    return [event async for event in stream]
