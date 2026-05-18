"""Coverage for optional agent adapters without external runtimes."""

from __future__ import annotations

import asyncio
import os
import sys
import types
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from AutoGLM_GUI.actions import ActionResult
from AutoGLM_GUI.agents.droidrun.async_agent import DroidRunAgent
from AutoGLM_GUI.agents.gemini.async_agent import AsyncGeminiAgent
from AutoGLM_GUI.agents.mai.async_agent import AsyncMAIAgent
from AutoGLM_GUI.agents.midscene.async_agent import AsyncMidsceneAgent
from AutoGLM_GUI.agents.qwen.async_agent import AsyncQwenAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import Screenshot


PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


async def _collect(agen: AsyncGenerator[dict[str, Any], None]) -> list[dict[str, Any]]:
    return [event async for event in agen]


class FakeDevice:
    device_id = "device-1"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        if self.fail:
            raise RuntimeError("screen failed")
        return Screenshot(base64_data=PNG_1X1_BASE64, width=100, height=200)

    def get_current_app(self) -> str:
        if self.fail:
            raise RuntimeError("app failed")
        return "com.example"


def _install_fake_droidrun(monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> type:
    class CodeActResponseEvent:
        def __init__(self, thought: str = "") -> None:
            self.thought = thought

    class CodeActResultEvent:
        def __init__(self) -> None:
            self.summary = "code summary"
            self.action = "tap"
            self.success = True

    class FastAgentResultEvent:
        def __init__(self) -> None:
            self.reason = "fast reason"
            self.instruction = "swipe"
            self.outcome = False

    class ExecutorResultEvent:
        def __init__(self) -> None:
            self.summary = "executor summary"
            self.action = "press"
            self.outcome = False
            self.error = "executor failed"

    class FinalizeEvent:
        reason = "wrapping up"

    class ManagerPlanEvent:
        def __init__(self, thought: str = "manager thought") -> None:
            self.thought = thought
            self.current_subgoal = "subgoal"

    class ResultEvent:
        success = True
        reason = "all done"
        steps = 9

    class DeviceConfig:
        def __init__(self, serial: str) -> None:
            self.serial = serial

    class DroidConfig:
        def __init__(self) -> None:
            self.device = None
            self.telemetry = SimpleNamespace(enabled=True)
            self.agent = SimpleNamespace(max_steps=0, reasoning=True)

    class FakeHandler:
        cancelled = False

        async def stream_events(self):
            for event in events:
                yield event

        def cancel(self) -> None:
            self.cancelled = True

    class DroidAgent:
        created: list[dict[str, Any]] = []
        fail_init = False

        def __init__(self, goal: str, llms: Any, config: DroidConfig) -> None:
            if self.fail_init:
                raise RuntimeError("init failed")
            self.created.append({"goal": goal, "llms": llms, "config": config})

        def run(self) -> FakeHandler:
            return FakeHandler()

    modules = {
        "droidrun": types.ModuleType("droidrun"),
        "droidrun.agent": types.ModuleType("droidrun.agent"),
        "droidrun.agent.codeact": types.ModuleType("droidrun.agent.codeact"),
        "droidrun.agent.codeact.events": types.ModuleType(
            "droidrun.agent.codeact.events"
        ),
        "droidrun.agent.droid": types.ModuleType("droidrun.agent.droid"),
        "droidrun.agent.droid.events": types.ModuleType("droidrun.agent.droid.events"),
        "droidrun.agent.droid.droid_agent": types.ModuleType(
            "droidrun.agent.droid.droid_agent"
        ),
        "droidrun.agent.utils": types.ModuleType("droidrun.agent.utils"),
        "droidrun.agent.utils.llm_picker": types.ModuleType(
            "droidrun.agent.utils.llm_picker"
        ),
        "droidrun.config_manager": types.ModuleType("droidrun.config_manager"),
        "droidrun.config_manager.config_manager": types.ModuleType(
            "droidrun.config_manager.config_manager"
        ),
    }

    modules["droidrun.agent.codeact.events"].CodeActResponseEvent = CodeActResponseEvent
    droid_events = modules["droidrun.agent.droid.events"]
    droid_events.CodeActResultEvent = CodeActResultEvent
    droid_events.FastAgentResultEvent = FastAgentResultEvent
    droid_events.ExecutorResultEvent = ExecutorResultEvent
    droid_events.FinalizeEvent = FinalizeEvent
    droid_events.ManagerPlanEvent = ManagerPlanEvent
    droid_events.ResultEvent = ResultEvent
    modules["droidrun.agent.droid"].events = droid_events
    modules["droidrun.agent.droid.droid_agent"].DroidAgent = DroidAgent
    modules["droidrun.agent.utils.llm_picker"].load_llm = lambda *a, **k: "llm"
    modules["droidrun.config_manager.config_manager"].DeviceConfig = DeviceConfig
    modules["droidrun.config_manager.config_manager"].DroidConfig = DroidConfig

    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    return SimpleNamespace(
        CodeActResponseEvent=CodeActResponseEvent,
        CodeActResultEvent=CodeActResultEvent,
        FastAgentResultEvent=FastAgentResultEvent,
        ExecutorResultEvent=ExecutorResultEvent,
        FinalizeEvent=FinalizeEvent,
        ManagerPlanEvent=ManagerPlanEvent,
        ResultEvent=ResultEvent,
        DroidAgent=DroidAgent,
        llm_picker=modules["droidrun.agent.utils.llm_picker"],
    )


def test_droidrun_agent_converts_fake_runtime_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[Any] = []
    fake = _install_fake_droidrun(monkeypatch, events)
    events.extend(
        [
            fake.CodeActResponseEvent("code thought"),
            fake.CodeActResponseEvent(""),
            fake.CodeActResultEvent(),
            fake.FastAgentResultEvent(),
            fake.ManagerPlanEvent(),
            fake.ManagerPlanEvent(""),
            fake.ExecutorResultEvent(),
            fake.FinalizeEvent(),
            fake.ResultEvent(),
        ]
    )
    agent = DroidRunAgent(ModelConfig(), AgentConfig(max_steps=None), FakeDevice())

    collected = asyncio.run(_collect(agent.stream("do it")))

    assert collected[0]["type"] == "thinking"
    assert [event["type"] for event in collected[1:]] == [
        "thinking",
        "step",
        "step",
        "thinking",
        "thinking",
        "step",
        "thinking",
        "done",
    ]
    assert collected[2]["data"]["action"]["description"] == "tap"
    assert collected[3]["data"]["success"] is False
    assert collected[-1]["data"] == {"success": True, "message": "all done", "steps": 9}

    assert agent.step_count == 3
    assert agent.context == []
    assert agent.is_running is False
    assert asyncio.run(agent.run("do it")) == "all done"
    asyncio.run(agent.cancel())
    assert agent._cancel_event.is_set()
    agent.reset()
    assert agent.step_count == 0


def test_droidrun_agent_reports_import_llm_init_and_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = DroidRunAgent(ModelConfig(), AgentConfig(), FakeDevice())
    missing = asyncio.run(_collect(agent.stream("task")))
    assert missing[-1]["type"] == "error"
    assert "droidrun" in missing[-1]["data"]["message"]

    fake = _install_fake_droidrun(monkeypatch, [])
    fake.llm_picker.load_llm = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("llm failed")
    )
    llm_error = asyncio.run(_collect(agent.stream("task")))
    assert llm_error[-1]["data"]["message"] == "LLM 加载失败：llm failed"

    fake = _install_fake_droidrun(monkeypatch, [])
    fake.DroidAgent.fail_init = True
    init_error = asyncio.run(_collect(agent.stream("task")))
    assert init_error[-1]["data"]["message"] == "DroidAgent 初始化失败：init failed"

    _install_fake_droidrun(monkeypatch, [RuntimeError("not an event")])

    class BadHandler:
        async def stream_events(self):
            raise RuntimeError("runtime failed")
            yield None

        def cancel(self) -> None:
            pass

    class BadAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run(self) -> BadHandler:
            return BadHandler()

    sys.modules["droidrun.agent.droid.droid_agent"].DroidAgent = BadAgent
    runtime_error = asyncio.run(_collect(agent.stream("task")))
    assert runtime_error[-1]["data"]["message"] == "执行错误：runtime failed"


def _midscene_agent() -> AsyncMidsceneAgent:
    return AsyncMidsceneAgent(
        ModelConfig(
            base_url="https://example.test/v1",
            api_key="key",
            model_name="vision",
            extra_body={"model_family": "qwen"},
        ),
        AgentConfig(max_steps=7),
        FakeDevice(),
    )


def test_midscene_env_detection_and_stream_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        AsyncMidsceneAgent, "_get_shell_path", classmethod(lambda cls: "/bin")
    )
    monkeypatch.setattr(AsyncMidsceneAgent, "_find_npx", classmethod(lambda cls: None))
    monkeypatch.setattr(
        AsyncMidsceneAgent, "_detect_android_home", staticmethod(lambda: "/sdk")
    )
    monkeypatch.delenv("ANDROID_HOME", raising=False)

    agent = _midscene_agent()
    env = agent._build_env()
    no_npx = asyncio.run(_collect(agent.stream("tap")))

    assert env["DEBUG"] == "midscene:*"
    assert env["MIDSCENE_MODEL_API_KEY"] == "key"
    assert env["MIDSCENE_MODEL_BASE_URL"] == "https://example.test/v1"
    assert env["MIDSCENE_MODEL_NAME"] == "vision"
    assert env["MIDSCENE_MODEL_FAMILY"] == "qwen"
    assert env["MIDSCENE_REPLANNING_CYCLE_LIMIT"] == "7"
    assert env["ANDROID_HOME"] == "/sdk"
    assert no_npx[-1]["type"] == "error"

    commands: list[list[str]] = []

    async def fake_run_command(args, env, cwd, timeout=60):
        commands.append(args)
        return ("connect" not in args, "connect failed")

    monkeypatch.setattr(AsyncMidsceneAgent, "_find_npx", classmethod(lambda cls: "npx"))
    monkeypatch.setattr(agent, "_run_command", fake_run_command)
    connect_fail = asyncio.run(_collect(agent.stream("tap")))
    assert connect_fail[-1]["data"]["message"].startswith("Midscene 连接设备失败")
    assert commands[-1][-1] == "disconnect"

    async def fake_run_command_ok(args, env, cwd, timeout=60):
        commands.append(args)
        return True, "ok"

    async def fake_act(args, env, cwd):
        yield {"type": "done", "data": {"message": "done", "steps": 1, "success": True}}

    monkeypatch.setattr(agent, "_run_command", fake_run_command_ok)
    monkeypatch.setattr(agent, "_run_act_streaming", fake_act)
    monkeypatch.setattr("tempfile.mkdtemp", lambda prefix: str(tmp_path / prefix))
    monkeypatch.setattr(os, "rmdir", lambda path: None)

    success = asyncio.run(_collect(agent.stream("tap")))
    assert success[-1]["data"]["message"] == "done"


def test_midscene_run_command_success_timeout_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _midscene_agent()

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"ok", None

    async def fake_create(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    ok, output = asyncio.run(agent._run_command(["npx"], {}, "/tmp"))
    assert (ok, output) == (True, "ok")

    async def timeout_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", timeout_wait_for)
    ok, output = asyncio.run(agent._run_command(["npx"], {}, "/tmp"))
    assert (ok, output) == (False, "命令执行超时")

    async def exploding_create(*args, **kwargs):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", exploding_create)
    ok, output = asyncio.run(agent._run_command(["npx"], {}, "/tmp"))
    assert (ok, output) == (False, "spawn failed")


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode() for line in lines] + [b""]

    async def readline(self) -> bytes:
        return self._lines.pop(0)


class FakeMidsceneProcess:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = FakeStdout(lines)
        self.returncode = returncode
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    async def wait(self) -> None:
        return None


def test_midscene_run_act_streaming_success_error_and_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _midscene_agent()
    plan = (
        '{"thought": "inspect", "log": "tap", '
        '"action": {"type": "Tap", "param": {"x": 1}}, '
        '"shouldContinuePlanning": false}'
    )
    lines = [
        "2026-05-19T01:02:03.456Z midscene:ai:call response reasoning content: think\n",
        "2026-05-19T01:02:03.456Z midscene:agent:task-builder calling action Tap\n",
        "2026-05-19T01:02:03.456Z midscene:device-task-executor planResult "
        + plan
        + "\n",
        "Task finished, message: done\n",
    ]

    async def fake_create(*args, **kwargs):
        return FakeMidsceneProcess(lines)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    events = asyncio.run(_collect(agent._run_act_streaming(["npx"], {}, "/tmp")))
    assert [event["type"] for event in events] == [
        "thinking",
        "thinking",
        "step",
        "done",
    ]
    assert events[2]["data"]["action"]["param"] == {"x": 1}

    async def fake_error_create(*args, **kwargs):
        return FakeMidsceneProcess(["Error: unable to click\n"], returncode=2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_error_create)
    error_events = asyncio.run(_collect(agent._run_act_streaming(["npx"], {}, "/tmp")))
    assert error_events[-1]["type"] == "error"
    assert "unable to click" in error_events[-1]["data"]["message"]

    async def fake_cancel_create(*args, **kwargs):
        return FakeMidsceneProcess([])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_cancel_create)
    agent._cancel_event.set()
    cancel_events = asyncio.run(_collect(agent._run_act_streaming(["npx"], {}, "/tmp")))
    assert cancel_events == [{"type": "cancelled", "data": {"message": "任务已取消"}}]

    async def fake_start_error(*args, **kwargs):
        raise RuntimeError("no process")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_start_error)
    start_error = asyncio.run(_collect(agent._run_act_streaming(["npx"], {}, "/tmp")))
    assert start_error[-1]["data"]["message"] == "启动 Midscene 失败：no process"


def _tool_response(action: dict[str, Any]) -> str:
    import json

    return (
        "<thinking>tap it</thinking><tool_call>"
        + json.dumps({"name": "mobile_use", "arguments": action})
        + "</tool_call>"
    )


def _make_mai_agent(device: FakeDevice | None = None) -> AsyncMAIAgent:
    return AsyncMAIAgent(
        ModelConfig(model_name="mai-model"),
        AgentConfig(max_steps=3, verbose=True),
        device or FakeDevice(),
        history_n=2,
    )


def _make_qwen_agent(
    device: FakeDevice | None = None, *, verbose: bool = True
) -> AsyncQwenAgent:
    return AsyncQwenAgent(
        ModelConfig(model_name="qwen-model"),
        AgentConfig(max_steps=3, verbose=verbose),
        device or FakeDevice(),
    )


def _make_gemini_agent(
    device: FakeDevice | None = None, *, verbose: bool = True
) -> AsyncGeminiAgent:
    return AsyncGeminiAgent(
        ModelConfig(model_name="gemini-model"),
        AgentConfig(max_steps=3, verbose=verbose),
        device or FakeDevice(),
    )


def test_mai_agent_execute_step_success_action_failure_and_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_mai_agent()
    agent._prepare_initial_context("task", PNG_1X1_BASE64, "app")

    async def fake_stream(messages):
        yield {"type": "thinking", "content": "partial"}
        yield {
            "type": "raw",
            "content": _tool_response({"action": "click", "coordinate": [500, 500]}),
        }

    monkeypatch.setattr(agent, "_stream_openai", fake_stream)
    monkeypatch.setattr(
        agent.action_handler,
        "execute",
        lambda action, width, height: ActionResult(
            success=True, should_finish=False, message="ok"
        ),
    )

    events = asyncio.run(_collect(agent._execute_step()))
    assert [event["type"] for event in events] == ["thinking", "step"]
    assert events[-1]["data"]["action"]["element"] == [500, 500]
    assert events[-1]["data"]["success"] is True
    assert len(agent.traj_memory) == 1

    async def finish_stream(messages):
        yield {"type": "raw", "content": _tool_response({"action": "terminate"})}

    def raise_action(*args, **kwargs):
        raise RuntimeError("action failed")

    monkeypatch.setattr(agent, "_stream_openai", finish_stream)
    monkeypatch.setattr(agent.action_handler, "execute", raise_action)
    failed_action = asyncio.run(_collect(agent._execute_step()))
    assert failed_action[-1]["data"]["finished"] is True
    assert failed_action[-1]["data"]["success"] is False

    messages = agent._build_messages("task", "screen", PNG_1X1_BASE64)
    assert len(messages) == 5
    agent.reset()
    assert len(agent.traj_memory) == 0


def test_mai_agent_execute_step_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    device_error_agent = _make_mai_agent(FakeDevice(fail=True))
    device_events = asyncio.run(_collect(device_error_agent._execute_step()))
    assert [event["type"] for event in device_events] == ["error", "step"]
    assert device_events[-1]["data"]["finished"] is True

    parse_agent = _make_mai_agent()

    async def bad_parse_stream(messages):
        yield {"type": "raw", "content": "not xml"}

    monkeypatch.setattr(parse_agent, "_stream_openai", bad_parse_stream)
    parse_events = asyncio.run(_collect(parse_agent._execute_step()))
    assert parse_events[-2]["data"]["message"].startswith("Parse error:")
    assert "after 3 retries" in parse_events[-1]["data"]["message"]

    model_agent = _make_mai_agent()

    async def broken_stream(messages):
        raise RuntimeError("model failed")
        yield {}

    monkeypatch.setattr(model_agent, "_stream_openai", broken_stream)
    model_events = asyncio.run(_collect(model_agent._execute_step()))
    assert model_events[-2]["data"]["message"] == "Model error: model failed"
    assert "after 3 retries" in model_events[-1]["data"]["message"]


def test_mai_stream_openai_splits_thinking_and_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_mai_agent()

    class FakeDelta:
        def __init__(self, content: str | None) -> None:
            self.content = content

    class FakeChoice:
        def __init__(self, content: str | None) -> None:
            self.delta = FakeDelta(content)

    class FakeChunk:
        def __init__(self, content: str | None = None, empty: bool = False) -> None:
            self.choices = [] if empty else [FakeChoice(content)]

    class FakeStream:
        def __init__(self) -> None:
            self.closed = False
            self.chunks = [
                FakeChunk("hello "),
                FakeChunk("<think", empty=True),
                FakeChunk("<tool_call>{}</tool_call>"),
            ]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.chunks:
                raise StopAsyncIteration
            return self.chunks.pop(0)

        async def close(self) -> None:
            self.closed = True

    fake_stream = FakeStream()

    class FakeCompletions:
        async def create(self, **kwargs):
            return fake_stream

    agent.openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )

    events = asyncio.run(
        _collect(agent._stream_openai([{"role": "user", "content": "x"}]))
    )
    assert events[0] == {"type": "raw", "content": "hello "}
    assert {"type": "thinking", "content": "hello "} in events
    assert events[-1]["type"] == "raw"
    assert fake_stream.closed is True


def test_qwen_agent_execute_step_error_debug_and_action_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agent = _make_qwen_agent()
    monkeypatch.chdir(tmp_path)

    debug_path = agent._draw_tap_debug(PNG_1X1_BASE64, 1, 1, "Tap", 1)
    assert debug_path is not None
    assert Path(debug_path).exists()
    assert agent._draw_tap_debug("not-base64", 1, 1, "Tap", 2) is None

    device_error_agent = _make_qwen_agent(FakeDevice(fail=True))
    device_events = asyncio.run(_collect(device_error_agent._execute_step()))
    assert [event["type"] for event in device_events] == ["error", "step"]
    assert device_events[-1]["data"]["message"] == "Device error: screen failed"

    model_error_agent = _make_qwen_agent()

    async def broken_stream(messages):
        raise RuntimeError("model failed")
        yield {}

    monkeypatch.setattr(model_error_agent, "_stream_openai", broken_stream)
    model_events = asyncio.run(_collect(model_error_agent._execute_step()))
    assert model_events[-2]["data"]["message"] == "Model error: model failed"
    assert model_events[-1]["data"]["finished"] is True

    parse_fallback_agent = _make_qwen_agent()

    async def invalid_action_stream(messages):
        yield {"type": "thinking", "content": "thinking"}
        yield {"type": "raw", "content": "not a qwen action"}

    def raise_action(*args, **kwargs):
        raise RuntimeError("action failed")

    monkeypatch.setattr(parse_fallback_agent, "_stream_openai", invalid_action_stream)
    monkeypatch.setattr(parse_fallback_agent.action_handler, "execute", raise_action)
    fallback_events = asyncio.run(_collect(parse_fallback_agent._execute_step()))
    assert [event["type"] for event in fallback_events] == ["thinking", "step"]
    assert fallback_events[-1]["data"]["action"]["_metadata"] == "finish"
    assert fallback_events[-1]["data"]["success"] is False
    assert fallback_events[-1]["data"]["message"] == "action failed"

    tap_agent = _make_qwen_agent()

    async def tap_stream(messages):
        yield {
            "type": "raw",
            "content": '<answer>do(action="Tap", element=[500, 500])</answer>',
        }

    monkeypatch.setattr(tap_agent, "_stream_openai", tap_stream)
    monkeypatch.setattr(
        tap_agent.action_handler,
        "execute",
        lambda *a, **k: ActionResult(
            success=True, should_finish=True, message="tapped"
        ),
    )
    tap_events = asyncio.run(_collect(tap_agent._execute_step()))
    assert tap_events[-1]["data"]["action"]["action"] == "Tap"
    assert tap_events[-1]["data"]["message"] == "tapped"


def test_qwen_stream_openai_streaming_and_cancel_paths() -> None:
    agent = _make_qwen_agent(verbose=False)

    class FakeDelta:
        def __init__(self, content: str | None) -> None:
            self.content = content

    class FakeChoice:
        def __init__(self, content: str | None) -> None:
            self.delta = FakeDelta(content)

    class FakeChunk:
        def __init__(self, content: str | None = None, *, empty: bool = False) -> None:
            self.choices = [] if empty else [FakeChoice(content)]

    class FakeStream:
        def __init__(self, chunks: list[FakeChunk]) -> None:
            self.chunks = chunks
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.chunks:
                raise StopAsyncIteration
            return self.chunks.pop(0)

        async def close(self) -> None:
            self.closed = True

    fake_stream = FakeStream(
        [
            FakeChunk("thinking "),
            FakeChunk(empty=True),
            FakeChunk('<answer>finish(message="done")</answer>'),
            FakeChunk("ignored action text"),
        ]
    )

    class FakeCompletions:
        async def create(self, **kwargs):
            return fake_stream

    agent.openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )

    events = asyncio.run(_collect(agent._stream_openai([{"role": "user"}])))
    assert events[0] == {"type": "raw", "content": "thinking "}
    assert {"type": "thinking", "content": "thinking "} in events
    assert events[-1] == {"type": "raw", "content": "ignored action text"}
    assert fake_stream.closed is True

    cancelled_stream = FakeStream([FakeChunk("cancel")])

    class CancelCompletions:
        async def create(self, **kwargs):
            return cancelled_stream

    agent.openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=CancelCompletions())
    )
    agent._cancel_event.set()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_collect(agent._stream_openai([{"role": "user"}])))
    assert cancelled_stream.closed is True


def test_gemini_agent_execute_step_and_llm_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_gemini_agent()
    agent._prepare_initial_context("tap", PNG_1X1_BASE64, "app")

    async def tap_tool():
        return "think", None, "tap", {"x": 1, "y": 2}

    monkeypatch.setattr(agent, "_call_llm_with_tools", tap_tool)
    monkeypatch.setattr(
        agent.action_handler,
        "execute",
        lambda *a, **k: ActionResult(success=True, should_finish=False, message="ok"),
    )
    success_events = asyncio.run(_collect(agent._execute_step()))
    assert [event["type"] for event in success_events] == ["thinking", "step"]
    assert success_events[-1]["data"]["action"]["action"] == "Tap"
    assert success_events[-1]["data"]["success"] is True

    action_error_agent = _make_gemini_agent()
    action_error_agent._prepare_initial_context("tap", PNG_1X1_BASE64, "app")

    async def back_tool():
        return "", None, "back", {}

    def raise_action(*args, **kwargs):
        raise RuntimeError("tap failed")

    monkeypatch.setattr(action_error_agent, "_call_llm_with_tools", back_tool)
    monkeypatch.setattr(action_error_agent.action_handler, "execute", raise_action)
    action_error_events = asyncio.run(_collect(action_error_agent._execute_step()))
    assert action_error_events[-1]["data"]["success"] is False
    assert action_error_events[-1]["data"]["finished"] is True
    assert action_error_events[-1]["data"]["message"] == "tap failed"

    model_error_agent = _make_gemini_agent()

    async def broken_tool():
        raise RuntimeError("model failed")

    monkeypatch.setattr(model_error_agent, "_call_llm_with_tools", broken_tool)
    model_events = asyncio.run(_collect(model_error_agent._execute_step()))
    assert [event["type"] for event in model_events] == ["error", "step"]
    assert model_events[-1]["data"]["message"] == "Model error: model failed"

    device_error_agent = _make_gemini_agent(FakeDevice(fail=True))
    device_error_agent._step_count = 1
    device_events = asyncio.run(_collect(device_error_agent._execute_step()))
    assert [event["type"] for event in device_events] == ["error", "step"]
    assert device_events[-1]["data"]["message"] == "Device error: screen failed"


def test_gemini_call_llm_with_tools_parses_tool_no_tool_bad_json_and_cancel() -> None:
    agent = _make_gemini_agent()
    agent._prepare_initial_context("tap", PNG_1X1_BASE64, "app")

    class FakeCompletions:
        def __init__(self, message: Any) -> None:
            self.message = message

        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=self.message)])

    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="tap", arguments='{"x": 1, "y": 2}')
    )
    agent.openai_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=FakeCompletions(
                SimpleNamespace(content="thinking", tool_calls=[tool_call])
            )
        )
    )
    assert asyncio.run(agent._call_llm_with_tools()) == (
        "thinking",
        None,
        "tap",
        {"x": 1, "y": 2},
    )

    no_tool_agent = _make_gemini_agent()
    no_tool_agent.openai_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=FakeCompletions(SimpleNamespace(content="done", tool_calls=[]))
        )
    )
    assert asyncio.run(no_tool_agent._call_llm_with_tools()) == (
        "done",
        None,
        "finish",
        {"message": "done"},
    )

    bad_json_agent = _make_gemini_agent()
    bad_tool_call = SimpleNamespace(
        function=SimpleNamespace(name="tap", arguments="{bad")
    )
    bad_json_agent.openai_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=FakeCompletions(
                SimpleNamespace(content="", tool_calls=[bad_tool_call])
            )
        )
    )
    assert asyncio.run(bad_json_agent._call_llm_with_tools()) == ("", None, "tap", {})

    cancelled_agent = _make_gemini_agent()
    cancelled_agent._cancel_event.set()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancelled_agent._call_llm_with_tools())
