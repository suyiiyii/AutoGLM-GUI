"""Tests for the MobileForge protocol adapter."""

import asyncio

import pytest

from AutoGLM_GUI.actions import ActionResult
from AutoGLM_GUI.agents.mobileforge.async_agent import AsyncMobileForgeAgent
from AutoGLM_GUI.agents.mobileforge.parser import MobileForgeParser
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import Screenshot


class _FakeDevice:
    device_id = "mobileforge-test"

    def get_screenshot(self, timeout: int = 10) -> Screenshot:  # noqa: ARG002
        return Screenshot(base64_data="image", width=1080, height=2400)

    def get_current_app(self) -> str:
        return "com.example.app"


class TestMobileForgeParser:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (
                '<thinking>tap it</thinking><tool_call>{"action":"click","coordinate":[12,999]}</tool_call>',
                {"_metadata": "do", "action": "Tap", "element": [12, 999]},
            ),
            (
                '<tool_call>{"action":"swipe","start":[100,200],"end":[300,400]}</tool_call>',
                {"_metadata": "do", "action": "Swipe", "start": [100, 200], "end": [300, 400]},
            ),
            (
                '<tool_call>{"action":"type","text":"hello"}</tool_call>',
                {"_metadata": "do", "action": "Type", "text": "hello"},
            ),
            (
                '<tool_call>{"action":"system_button","button":"home"}</tool_call>',
                {"_metadata": "do", "action": "Home"},
            ),
            (
                '<tool_call>{"action":"terminate","status":"success"}</tool_call>',
                {"_metadata": "finish", "message": "Task completed"},
            ),
        ],
    )
    def test_translates_supported_actions(self, content, expected):
        parser = MobileForgeParser()
        thinking, action = parser.parse_response(content)
        assert parser.parse(action) == expected
        assert isinstance(thinking, str)

    def test_rejects_missing_or_unsafe_calls(self):
        parser = MobileForgeParser()
        thinking, action = parser.parse_response("plain text")
        assert thinking == ""
        with pytest.raises(ValueError, match="Invalid"):
            parser.parse(action)
        with pytest.raises(ValueError, match="two-number"):
            parser.parse('{"action":"click","coordinate":"bad"}')
        with pytest.raises(ValueError, match="Unsupported"):
            parser.parse('{"action":"shell"}')


def test_mobileforge_agent_preserves_native_assistant_context(monkeypatch):
    agent = AsyncMobileForgeAgent(
        model_config=ModelConfig(),
        agent_config=AgentConfig(max_steps=2, verbose=False),
        device=_FakeDevice(),
    )
    response = (
        '<thinking>the app is open</thinking>'
        '<tool_call>{"action":"terminate","status":"success"}</tool_call>'
    )

    async def fake_stream(messages):  # noqa: ARG001
        yield {"type": "raw", "content": response}

    monkeypatch.setattr(agent, "_stream_openai", fake_stream)
    monkeypatch.setattr(
        agent.action_handler,
        "execute",
        lambda *args, **kwargs: ActionResult(True, True, "done"),
    )

    async def run() -> None:
        agent._prepare_initial_context("finish", "image", "com.example.app")
        async for _ in agent._execute_step():
            pass

    asyncio.run(run())
    assert agent._context[-1]["content"] == response


def test_mobileforge_agent_is_registered():
    from AutoGLM_GUI.agents import is_agent_type_registered

    assert is_agent_type_registered("mobileforge")
