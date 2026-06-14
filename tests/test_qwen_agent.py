"""Tests for Qwen agent components (QwenParser, AsyncQwenAgent, registration)."""

import asyncio
import copy
from typing import Any

import pytest

from AutoGLM_GUI.actions import ActionResult
from AutoGLM_GUI.agents.qwen.async_agent import AsyncQwenAgent
from AutoGLM_GUI.agents.qwen.parser import QwenParser
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


def _text_part(message: dict[str, Any]) -> str:
    return next(
        part["text"]
        for part in message["content"]
        if isinstance(part, dict) and part.get("type") == "text"
    )


class _FakeDevice:
    device_id = "fake-001"

    def __init__(self) -> None:
        self._n = 0

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        self._n += 1
        return Screenshot(base64_data=f"img{self._n}", width=1080, height=2400)

    def get_current_app(self) -> str:
        return "com.example.app"


def _make_agent() -> AsyncQwenAgent:
    return AsyncQwenAgent(
        model_config=ModelConfig(),
        agent_config=AgentConfig(max_steps=10, verbose=False),
        device=_FakeDevice(),
    )


async def _drain(agen) -> None:
    async for _ in agen:
        pass


# ---------------------------------------------------------------------------
# QwenParser
# ---------------------------------------------------------------------------


class TestQwenParser:
    def test_parse_tap(self):
        parser = QwenParser()
        result = parser.parse('do(action="Tap", element=[500, 300])')
        assert result["_metadata"] == "do"
        assert result["action"] == "Tap"
        assert result["element"] == [500, 300]

    def test_parse_launch(self):
        parser = QwenParser()
        result = parser.parse('do(action="Launch", app="WeChat")')
        assert result["_metadata"] == "do"
        assert result["action"] == "Launch"
        assert result["app"] == "WeChat"

    def test_parse_type(self):
        parser = QwenParser()
        result = parser.parse('do(action="Type", text="hello")')
        assert result["_metadata"] == "do"
        assert result["action"] == "Type"
        assert result["text"] == "hello"

    def test_parse_swipe(self):
        parser = QwenParser()
        result = parser.parse('do(action="Swipe", start=[100, 200], end=[300, 400])')
        assert result["_metadata"] == "do"
        assert result["action"] == "Swipe"
        assert result["start"] == [100, 200]
        assert result["end"] == [300, 400]

    def test_parse_finish(self):
        parser = QwenParser()
        result = parser.parse('finish(message="done")')
        assert result["_metadata"] == "finish"
        assert result["message"] == "done"

    def test_parse_info(self):
        parser = QwenParser()
        result = parser.parse('info(question="which one?")')
        assert result["_metadata"] == "info"
        assert result["question"] == "which one?"

    def test_parse_answer_tags(self):
        parser = QwenParser()
        result = parser.parse('<answer>do(action="Tap", element=[100, 200])</answer>')
        assert result["_metadata"] == "do"
        assert result["element"] == [100, 200]

    def test_parse_answer_wraps_correctly(self):
        parser = QwenParser()
        result = parser.parse('do(action="Tap", element=[500, 300])')
        assert result["_metadata"] == "do"
        assert result["element"] == [500, 300]

    def test_parse_unknown_raises(self):
        parser = QwenParser()
        with pytest.raises(ValueError):
            parser.parse("unknown_format()")

    def test_coordinate_scale(self):
        parser = QwenParser()
        assert parser.coordinate_scale == 1000


class TestQwenParserResponse:
    def test_parse_response_with_answer_tags(self):
        content = 'Let me think about this.<answer>do(action="Tap", element=[100, 200])</answer>'
        thinking, action = QwenParser.parse_response(content)
        assert "Let me think about this." in thinking
        assert 'do(action="Tap", element=[100, 200])' in action

    def test_parse_response_with_reasoning_tags(self):
        content = '<think>Let me analyze</think><answer>finish(message="done")</answer>'
        thinking, action = QwenParser.parse_response(content)
        assert "<think>" not in thinking
        assert "</think>" not in thinking
        assert "finish" in action

    def test_parse_response_keyword_finish_fallback(self):
        content = 'I\'m done.finish(message="completed")'
        thinking, action = QwenParser.parse_response(content)
        assert "I'm done." in thinking
        assert 'finish(message="completed")' in action

    def test_parse_response_keyword_do_fallback(self):
        content = 'Thinking...do(action="Back")'
        thinking, action = QwenParser.parse_response(content)
        assert "Thinking..." in thinking
        assert 'do(action="Back")' in action

    def test_parse_response_no_markers(self):
        content = "Just some text"
        thinking, action = QwenParser.parse_response(content)
        assert thinking == ""
        assert action == "Just some text"


# ---------------------------------------------------------------------------
# AsyncQwenAgent context invariant
# ---------------------------------------------------------------------------


class TestAsyncQwenAgentContext:
    def test_each_request_carries_exactly_one_image(self, monkeypatch):
        agent = _make_agent()

        captured: list[list[dict[str, Any]]] = []
        raw_responses = iter(
            [
                'I will tap the icon.<answer>do(action="Tap", element=[500, 500])</answer>',
                'All done.<answer>finish(message="ok")</answer>',
            ]
        )

        async def fake_stream(messages):
            captured.append(copy.deepcopy(messages))
            yield {"type": "raw", "content": next(raw_responses)}

        action_results = iter(
            [
                ActionResult(success=True, should_finish=False, message=None),
                ActionResult(success=True, should_finish=True, message="ok"),
            ]
        )

        monkeypatch.setattr(agent, "_stream_openai", fake_stream)
        monkeypatch.setattr(
            agent.action_handler, "execute", lambda *a, **k: next(action_results)
        )

        async def run() -> None:
            agent._prepare_initial_context(
                "play a song", "img0", "com.android.launcher"
            )
            await _drain(agent._execute_step())
            await _drain(agent._execute_step())

        asyncio.run(run())

        assert len(captured) == 2
        for request in captured:
            assert _count_images(request) == 1
            assert request[-1]["role"] == "user"

        assert "play a song" in _text_part(captured[0][-1])
        assert "play a song" not in _text_part(captured[1][-1])

    def test_context_retains_no_images_after_step(self, monkeypatch):
        agent = _make_agent()

        async def fake_stream(messages):
            yield {
                "type": "raw",
                "content": '<answer>do(action="Tap", element=[1, 1])</answer>',
            }

        monkeypatch.setattr(agent, "_stream_openai", fake_stream)
        monkeypatch.setattr(
            agent.action_handler,
            "execute",
            lambda *a, **k: ActionResult(
                success=True, should_finish=False, message=None
            ),
        )

        async def run() -> None:
            agent._prepare_initial_context("task", "img0", "app")
            await _drain(agent._execute_step())

        asyncio.run(run())
        assert _count_images(agent._context) == 0

    def test_user_reference_images_sent_on_first_request_only(self, monkeypatch):
        agent = _make_agent()

        captured: list[list[dict[str, Any]]] = []
        raw_responses = iter(
            [
                'I will tap.<answer>do(action="Tap", element=[500, 500])</answer>',
                'Done.<answer>finish(message="ok")</answer>',
            ]
        )

        async def fake_stream(messages):
            captured.append(copy.deepcopy(messages))
            yield {"type": "raw", "content": next(raw_responses)}

        action_results = iter(
            [
                ActionResult(success=True, should_finish=False, message=None),
                ActionResult(success=True, should_finish=True, message="ok"),
            ]
        )

        monkeypatch.setattr(agent, "_stream_openai", fake_stream)
        monkeypatch.setattr(
            agent.action_handler, "execute", lambda *a, **k: next(action_results)
        )

        async def run() -> None:
            agent._prepare_initial_context(
                "use the attached image",
                "img0",
                "com.android.launcher",
                reference_images=[{"mime_type": "image/jpeg", "data": "ref1"}],
            )
            await _drain(agent._execute_step())
            await _drain(agent._execute_step())

        asyncio.run(run())

        assert len(captured) == 2
        assert _count_images(captured[0]) == 2
        assert _count_images(captured[1]) == 1
        assert "User attached 1 reference image" in _text_part(captured[0][-1])


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


class TestQwenAgentRegistration:
    def test_qwen_registered(self):
        from AutoGLM_GUI.agents import is_agent_type_registered

        assert is_agent_type_registered("qwen")

    def test_qwen_in_list(self):
        from AutoGLM_GUI.agents import list_agent_types

        types = list_agent_types()
        assert "qwen" in types
