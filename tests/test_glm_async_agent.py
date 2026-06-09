"""Tests for AsyncGLMAgent multimodal context handling.

Regression coverage for issue #348: a stale initial screenshot leaked into
every LLM request (the per-step ``remove_images_from_message`` only stripped
the *last* message), so ``autoglm-phone`` saw two screenshots per turn and
produced wrong ``Tap`` coordinates. Each request must carry exactly one
screenshot — the current one — unless the user explicitly attached reference
images for the first turn. History must not retain images.
"""

import asyncio
import copy
from typing import Any

from AutoGLM_GUI.actions import ActionResult
from AutoGLM_GUI.agents.glm.async_agent import AsyncGLMAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import Screenshot
from AutoGLM_GUI.model import MessageBuilder


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


def _make_agent() -> AsyncGLMAgent:
    return AsyncGLMAgent(
        model_config=ModelConfig(),
        agent_config=AgentConfig(max_steps=10, verbose=False),
        device=_FakeDevice(),
    )


async def _drain(agen) -> None:
    async for _ in agen:
        pass


# ---------------------------------------------------------------------------
# MessageBuilder
# ---------------------------------------------------------------------------


def test_create_user_message_puts_image_first():
    msg = MessageBuilder.create_user_message("hello", image_base64="abc")
    assert [part["type"] for part in msg["content"]] == ["image_url", "text"]
    assert msg["content"][1]["text"] == "hello"


def test_remove_images_keeps_text_parts_as_list():
    msg = MessageBuilder.create_user_message("hello", image_base64="abc")
    stripped = MessageBuilder.remove_images_from_message(msg)

    assert isinstance(stripped["content"], list)
    assert _count_images([stripped]) == 0
    assert stripped["content"] == [{"type": "text", "text": "hello"}]


def test_remove_images_passes_through_string_content():
    msg = MessageBuilder.create_assistant_message("done")
    assert MessageBuilder.remove_images_from_message(msg) == msg


def test_create_user_message_with_images_preserves_order_and_mime_types():
    msg = MessageBuilder.create_user_message_with_images(
        "hello",
        [
            {"mime_type": "image/png", "data": "screen"},
            {"mime_type": "image/jpeg", "data": "reference"},
        ],
    )

    assert [part["type"] for part in msg["content"]] == [
        "image_url",
        "image_url",
        "text",
    ]
    assert msg["content"][0]["image_url"]["url"] == "data:image/png;base64,screen"
    assert msg["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,reference"
    assert msg["content"][2]["text"] == "hello"


# ---------------------------------------------------------------------------
# AsyncGLMAgent context invariant
# ---------------------------------------------------------------------------


def test_each_request_carries_exactly_one_image(monkeypatch):
    agent = _make_agent()

    captured: list[list[dict[str, Any]]] = []
    raw_responses = iter(
        [
            "I will tap the icon.\ndo(action=Tap(element=[500, 500]))",
            "All done.\nfinish(message=ok)",
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
        agent._prepare_initial_context("play a song", "img0", "com.android.launcher")
        await _drain(agent._execute_step())
        await _drain(agent._execute_step())

    asyncio.run(run())

    assert len(captured) == 2
    for request in captured:
        assert _count_images(request) == 1
        # the lone image must sit on the last (current) user message
        assert request[-1]["role"] == "user"
        assert any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for p in request[-1]["content"]
        )

    # task text is part of the first request, not repeated afterwards
    assert "play a song" in _text_part(captured[0][-1])
    assert "play a song" not in _text_part(captured[1][-1])


def test_context_retains_no_images_after_step(monkeypatch):
    agent = _make_agent()

    async def fake_stream(messages):
        yield {"type": "raw", "content": "do(action=Tap(element=[1, 1]))"}

    monkeypatch.setattr(agent, "_stream_openai", fake_stream)
    monkeypatch.setattr(
        agent.action_handler,
        "execute",
        lambda *a, **k: ActionResult(success=True, should_finish=False, message=None),
    )

    async def run() -> None:
        agent._prepare_initial_context("task", "img0", "app")
        await _drain(agent._execute_step())

    asyncio.run(run())

    assert _count_images(agent._context) == 0


def test_user_reference_images_are_sent_on_first_request_only(monkeypatch):
    agent = _make_agent()

    captured: list[list[dict[str, Any]]] = []
    raw_responses = iter(
        [
            "I will tap.\ndo(action=Tap(element=[500, 500]))",
            "Done.\nfinish(message=ok)",
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
# Zhipu Cloud API image format conversion
# ---------------------------------------------------------------------------


def test_zhipu_api_converts_image_url_to_extra_body(monkeypatch):
    """When base_url points to Zhipu Cloud, image_url parts are extracted
    to extra_body['image'] and messages are rebuilt with plain text content."""
    agent = AsyncGLMAgent(
        model_config=ModelConfig(
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model_name="autoglm-phone",
        ),
        agent_config=AgentConfig(max_steps=10, verbose=False),
        device=_FakeDevice(),
    )

    captured_kwargs: dict[str, Any] = {}

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)

        # Return an async iterator that yields one empty chunk
        class _FakeStream:
            async def __anext__(self):
                raise StopAsyncIteration

            def __aiter__(self):
                return self

            async def close(self):
                pass

        return _FakeStream()

    monkeypatch.setattr(agent.openai_client.chat.completions, "create", fake_create)

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,screenshot_b64"},
                },
                {"type": "text", "text": "Tap the icon."},
            ],
        },
    ]

    async def run() -> None:
        async for _ in agent._stream_openai(messages):
            pass

    asyncio.run(run())

    assert captured_kwargs["extra_body"]["image"] == "screenshot_b64"
    processed = captured_kwargs["messages"]
    assert processed[0]["content"] == "You are a helpful assistant."
    assert processed[1]["content"] == "Tap the icon."
    assert isinstance(processed[1]["content"], str)


def test_zhipu_api_uses_first_image_only(monkeypatch):
    """When multiple images are present, only the first is sent to extra_body."""
    agent = AsyncGLMAgent(
        model_config=ModelConfig(
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model_name="autoglm-phone",
        ),
        agent_config=AgentConfig(max_steps=10, verbose=False),
        device=_FakeDevice(),
    )

    captured_kwargs: dict[str, Any] = {}

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)

        class _FakeStream:
            async def __anext__(self):
                raise StopAsyncIteration

            def __aiter__(self):
                return self

            async def close(self):
                pass

        return _FakeStream()

    monkeypatch.setattr(agent.openai_client.chat.completions, "create", fake_create)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,first_img"},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,second_img"},
                },
                {"type": "text", "text": "Do this."},
            ],
        },
    ]

    async def run() -> None:
        async for _ in agent._stream_openai(messages):
            pass

    asyncio.run(run())

    assert captured_kwargs["extra_body"]["image"] == "first_img"
    assert captured_kwargs["messages"][0]["content"] == "Do this."


def test_non_zhipu_api_leaves_messages_untouched(monkeypatch):
    """Non-Zhipu endpoints keep the standard OpenAI vision format."""
    agent = AsyncGLMAgent(
        model_config=ModelConfig(
            base_url="http://localhost:8000/v1",
            model_name="autoglm-phone-9b",
        ),
        agent_config=AgentConfig(max_steps=10, verbose=False),
        device=_FakeDevice(),
    )

    captured_kwargs: dict[str, Any] = {}

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)

        class _FakeStream:
            async def __anext__(self):
                raise StopAsyncIteration

            def __aiter__(self):
                return self

            async def close(self):
                pass

        return _FakeStream()

    monkeypatch.setattr(agent.openai_client.chat.completions, "create", fake_create)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,img"},
                },
                {"type": "text", "text": "Tap."},
            ],
        },
    ]

    async def run() -> None:
        async for _ in agent._stream_openai(messages):
            pass

    asyncio.run(run())

    assert "image" not in captured_kwargs["extra_body"]
    assert captured_kwargs["messages"] == messages
