"""Tests for Gemini Agent components."""

import asyncio
import json
from typing import Any

import pytest

from AutoGLM_GUI.agents.gemini.action_mapper import (
    InvalidToolCallError,
    tool_call_to_action,
)
from AutoGLM_GUI.agents.gemini.async_agent import AsyncGeminiAgent
from AutoGLM_GUI.agents.gemini.tools import DEVICE_TOOLS
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import Screenshot


def _count_images(messages: list[dict[str, Any]]) -> int:
    count = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            count += sum(
                1
                for part in content
                if isinstance(part, dict) and part.get("type") == "image_url"
            )
    return count


class _FakeDevice:
    device_id = "fake-001"

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        return Screenshot(base64_data="screen", width=1080, height=2400)

    def get_current_app(self) -> str:
        return "com.example.app"


class _QueuedToolCallGeminiAgent(AsyncGeminiAgent):
    def __init__(self, tool_calls: list[tuple[str, str, dict[str, Any]]]):
        super().__init__(
            model_config=ModelConfig(),
            agent_config=AgentConfig(max_steps=10, verbose=False),
            device=_FakeDevice(),
        )
        self._tool_calls = tool_calls.copy()

    async def _call_llm_with_tools(self) -> tuple[str, str, dict[str, Any]]:
        if not self._tool_calls:
            return "", "finish", {"message": "No queued tool calls"}
        return self._tool_calls.pop(0)


class TestDeviceTools:
    def test_tool_count(self):
        assert len(DEVICE_TOOLS) == 10

    def test_all_tools_have_required_fields(self):
        for tool in DEVICE_TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_tool_names(self):
        names = {t["function"]["name"] for t in DEVICE_TOOLS}
        expected = {
            "tap",
            "double_tap",
            "long_press",
            "swipe",
            "type_text",
            "launch_app",
            "back",
            "home",
            "wait",
            "finish",
        }
        assert names == expected


class TestActionMapper:
    def test_tap(self):
        result = tool_call_to_action("tap", {"x": 500, "y": 300})
        assert result == {"_metadata": "do", "action": "Tap", "element": [500, 300]}

    def test_double_tap(self):
        result = tool_call_to_action("double_tap", {"x": 100, "y": 200})
        assert result == {
            "_metadata": "do",
            "action": "Double Tap",
            "element": [100, 200],
        }

    def test_long_press(self):
        result = tool_call_to_action("long_press", {"x": 750, "y": 800})
        assert result == {
            "_metadata": "do",
            "action": "Long Press",
            "element": [750, 800],
        }

    def test_swipe(self):
        result = tool_call_to_action(
            "swipe",
            {
                "start_x": 500,
                "start_y": 700,
                "end_x": 500,
                "end_y": 300,
            },
        )
        assert result == {
            "_metadata": "do",
            "action": "Swipe",
            "start": [500, 700],
            "end": [500, 300],
        }

    def test_type_text(self):
        result = tool_call_to_action("type_text", {"text": "Hello"})
        assert result == {"_metadata": "do", "action": "Type", "text": "Hello"}

    def test_launch_app(self):
        result = tool_call_to_action("launch_app", {"app_name": "WeChat"})
        assert result == {"_metadata": "do", "action": "Launch", "app": "WeChat"}

    def test_back(self):
        result = tool_call_to_action("back", {})
        assert result == {"_metadata": "do", "action": "Back"}

    def test_home(self):
        result = tool_call_to_action("home", {})
        assert result == {"_metadata": "do", "action": "Home"}

    def test_wait(self):
        result = tool_call_to_action("wait", {"duration": "2 seconds"})
        assert result == {"_metadata": "do", "action": "Wait", "duration": "2 seconds"}

    def test_finish(self):
        result = tool_call_to_action("finish", {"message": "Done"})
        assert result == {"_metadata": "finish", "message": "Done"}

    def test_unknown_tool(self):
        with pytest.raises(InvalidToolCallError, match="Unknown tool"):
            tool_call_to_action("unknown_tool", {})

    def test_missing_args_raise_invalid_tool_call(self):
        """Missing required args should be returned to the agent as tool errors."""
        with pytest.raises(InvalidToolCallError, match="Missing required argument"):
            tool_call_to_action("tap", {})

    def test_invalid_arg_type_raises_invalid_tool_call(self):
        """Non-numeric coordinates should not be converted into finish."""
        with pytest.raises(InvalidToolCallError, match="Expected number"):
            tool_call_to_action("tap", {"x": "click_here", "y": 100})

    def test_float_coords_converted_to_int(self):
        """Float coordinates from LLM should be accepted and converted."""
        result = tool_call_to_action("tap", {"x": 500.5, "y": 300.7})
        assert result == {"_metadata": "do", "action": "Tap", "element": [500, 300]}


class TestAgentRegistration:
    def test_gemini_registered(self):
        from AutoGLM_GUI.agents import is_agent_type_registered

        assert is_agent_type_registered("gemini")
        assert is_agent_type_registered("general-vision")

    def test_gemini_in_list(self):
        from AutoGLM_GUI.agents import list_agent_types

        types = list_agent_types()
        assert "gemini" in types
        assert "general-vision" in types


class TestGeminiImageAttachments:
    def test_initial_context_includes_reference_images_after_screen(self):
        from AutoGLM_GUI.agents.gemini.async_agent import AsyncGeminiAgent

        agent = AsyncGeminiAgent(
            model_config=ModelConfig(),
            agent_config=AgentConfig(max_steps=10, verbose=False),
            device=_FakeDevice(),
        )

        agent._prepare_initial_context(
            "compare this with the attached screenshot",
            "screen",
            "com.example.app",
            reference_images=[{"mime_type": "image/webp", "data": "reference"}],
        )

        assert _count_images(agent.context) == 2
        user_message = agent.context[-1]
        assert user_message["content"][0]["image_url"]["url"] == (
            "data:image/png;base64,screen"
        )
        assert user_message["content"][1]["image_url"]["url"] == (
            "data:image/webp;base64,reference"
        )
        assert "User attached 1 reference image" in user_message["content"][2]["text"]


class TestGeminiInvalidToolCalls:
    def test_invalid_tool_call_is_returned_as_retryable_tool_result(self):
        async def run():
            agent = _QueuedToolCallGeminiAgent(
                [("", "tap", {"x": "861, 365", "y": 100})]
            )
            agent._prepare_initial_context("tap the button", "screen", "app")
            events = [event async for event in agent._execute_step()]
            return agent, events

        agent, events = asyncio.run(run())

        assert len(events) == 1
        step = events[0]["data"]
        assert step["success"] is False
        assert step["finished"] is False
        assert step["action"]["_metadata"] == "tool_error"
        assert "Expected number" in step["message"]

        assistant_message = agent.context[-2]
        assert assistant_message["role"] == "assistant"
        assert assistant_message["tool_calls"][0]["function"]["name"] == "tap"
        assert (
            json.loads(assistant_message["tool_calls"][0]["function"]["arguments"])["x"]
            == "861, 365"
        )

        tool_message = agent.context[-1]
        assert tool_message["role"] == "tool"
        tool_result = json.loads(tool_message["content"])
        assert tool_result == {
            "success": False,
            "error_code": "invalid_tool_arguments",
            "message": step["message"],
            "retryable": True,
        }

    def test_invalid_tool_call_trace_marks_error(self, tmp_path, monkeypatch):
        trace_file = tmp_path / "trace.jsonl"
        monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")
        monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))

        async def run():
            agent = _QueuedToolCallGeminiAgent(
                [("", "tap", {"x": "861, 365", "y": 100})]
            )
            agent._prepare_initial_context("tap the button", "screen", "app")
            return [event async for event in agent._execute_step()]

        asyncio.run(run())

        records = [
            json.loads(line)
            for line in trace_file.read_text(encoding="utf-8").splitlines()
        ]
        tool_call = next(record for record in records if record["name"] == "tool.call")
        assert tool_call["attrs"]["success"] is False
        assert tool_call["attrs"]["error_kind"] == "invalid_arguments"
        assert "Expected number" in tool_call["attrs"]["error_message"]

    def test_repeated_invalid_tool_calls_finish_as_failed(self):
        async def run():
            agent = _QueuedToolCallGeminiAgent(
                [
                    ("", "tap", {"x": "861, 365", "y": 100}),
                    ("", "tap", {"x": "861, 365", "y": 100}),
                    ("", "tap", {"x": "861, 365", "y": 100}),
                ]
            )
            events = []
            async for event in agent.stream("tap the button"):
                events.append(event)
            return events

        events = asyncio.run(run())

        step_events = [event for event in events if event["type"] == "step"]
        assert len(step_events) == 3
        assert step_events[0]["data"]["finished"] is False
        assert step_events[-1]["data"]["success"] is False
        assert step_events[-1]["data"]["finished"] is True
        assert (
            "Tool call validation failed 3 consecutive times"
            in step_events[-1]["data"]["message"]
        )

        done_events = [event for event in events if event["type"] == "done"]
        assert len(done_events) == 1
        assert done_events[0]["data"]["success"] is False
        assert (
            "Tool call validation failed 3 consecutive times"
            in done_events[0]["data"]["message"]
        )


class TestEventTypes:
    def test_event_enum_matches_actual_events(self):
        """AgentEventType values must match the strings agents actually emit."""
        from AutoGLM_GUI.agents.events import AgentEventType

        assert AgentEventType.THINKING == "thinking"
        assert AgentEventType.STEP == "step"
        assert AgentEventType.DONE == "done"
        assert AgentEventType.ERROR == "error"
        assert AgentEventType.CANCELLED == "cancelled"


class TestCoordinateClamping:
    def test_clamp_negative_coordinates(self):
        from AutoGLM_GUI.actions.handler import ActionHandler

        handler = ActionHandler.__new__(ActionHandler)
        x, y = handler._convert_relative_to_absolute([-100, -50], 1080, 1920)
        assert x == 0
        assert y == 0

    def test_clamp_overflow_coordinates(self):
        from AutoGLM_GUI.actions.handler import ActionHandler

        handler = ActionHandler.__new__(ActionHandler)
        x, y = handler._convert_relative_to_absolute([1500, 2000], 1080, 1920)
        assert x == 1080
        assert y == 1920

    def test_normal_coordinates_unchanged(self):
        from AutoGLM_GUI.actions.handler import ActionHandler

        handler = ActionHandler.__new__(ActionHandler)
        x, y = handler._convert_relative_to_absolute([500, 500], 1080, 1920)
        assert x == 540
        assert y == 960
