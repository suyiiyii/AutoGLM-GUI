"""Coverage for managers and device implementations."""

from __future__ import annotations

import asyncio
import io
import stat
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import AutoGLM_GUI.adb_manager as adb_manager
import AutoGLM_GUI.agents as agents_module
import AutoGLM_GUI.agents.factory as factory
import AutoGLM_GUI.config_manager as config_manager_module
import AutoGLM_GUI.device_manager as device_manager_module
import AutoGLM_GUI.layered_agent_service as layered_agent_service
import AutoGLM_GUI.trace as trace_module
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.devices.mock_device import MockDevice, MockDeviceManager
from AutoGLM_GUI.devices.remote_device import RemoteDevice, RemoteDeviceManager
from AutoGLM_GUI.exceptions import (
    AgentInitializationError,
    AgentNotInitializedError,
    DeviceBusyError,
)
from AutoGLM_GUI.phone_agent_manager import (
    AgentMetadata,
    AgentState,
    PhoneAgentManager,
)
from AutoGLM_GUI.task_manager import TaskManager
from AutoGLM_GUI.task_store import TaskStatus, TaskStore


class FakeAgent:
    def __init__(self) -> None:
        self.reset_count = 0
        self.cancel_count = 0
        self.attachments: list[dict[str, Any]] = []
        self.stream_calls: list[tuple[str, str | None]] = []

    def reset(self) -> None:
        self.reset_count += 1

    async def cancel(self) -> None:
        self.cancel_count += 1

    def set_user_image_attachments(self, attachments: list[dict[str, Any]]) -> None:
        self.attachments = attachments

    async def stream(self, text: str, *, continue_with: str | None = None):
        self.stream_calls.append((text, continue_with))
        yield {
            "type": "thinking",
            "data": {"chunk": "thinking"},
        }
        yield {
            "type": "step",
            "data": {"step": 1, "thinking": "think", "action": {"action": "Tap"}},
        }
        yield {
            "type": "done",
            "data": {
                "message": f"done {text}",
                "success": True,
                "steps": 1,
            },
        }


class TakeoverResumeAgent(FakeAgent):
    async def stream(self, text: str, *, continue_with: str | None = None):
        self.stream_calls.append((text, continue_with))
        if continue_with is None:
            yield {
                "type": "step",
                "data": {
                    "step": 1,
                    "thinking": "need login",
                    "action": {"action": "Take_over", "message": "登录后继续"},
                    "waiting_for_input": True,
                    "success": True,
                    "finished": False,
                    "message": "TAKEOVER_REQUIRED:\n 登录后继续",
                },
            }
            yield {
                "type": "takeover",
                "data": {
                    "message": "TAKEOVER_REQUIRED:\n 登录后继续",
                    "steps": 1,
                    "success": True,
                    "stop_reason": "takeover",
                },
            }
            return

        yield {
            "type": "step",
            "data": {"step": 2, "thinking": "continued", "action": {"action": "Tap"}},
        }
        yield {
            "type": "done",
            "data": {
                "message": f"done {continue_with}",
                "success": True,
                "steps": 2,
            },
        }


class FakePhoneAgentManager:
    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.acquired: list[tuple[str, str | None]] = []
        self.released: list[tuple[str, str | None]] = []
        self.registered: list[tuple[str, str | None]] = []
        self.unregistered: list[tuple[str, str | None]] = []
        self.errors: list[tuple[str, str, str | None]] = []

    async def acquire_device_async(
        self,
        device_id: str,
        *,
        auto_initialize: bool = False,
        context: str | None = None,
    ) -> bool:
        self.acquired.append((device_id, context))
        return True

    def get_agent_with_context(self, device_id: str, **kwargs):
        return self.agent

    async def get_agent_with_context_async(self, device_id: str, **kwargs):
        return self.get_agent_with_context(device_id, **kwargs)

    def register_abort_handler(self, device_id: str, handler, context=None) -> None:
        self.registered.append((device_id, context))

    async def register_abort_handler_async(
        self, device_id: str, handler, context=None
    ) -> None:
        self.registered.append((device_id, context))

    def unregister_abort_handler(self, device_id: str, context=None) -> None:
        self.unregistered.append((device_id, context))

    async def unregister_abort_handler_async(
        self, device_id: str, context=None
    ) -> None:
        self.unregistered.append((device_id, context))

    def set_error_state(self, device_id: str, message: str, context=None) -> None:
        self.errors.append((device_id, message, context))

    async def set_error_state_async(
        self, device_id: str, message: str, context=None
    ) -> None:
        self.errors.append((device_id, message, context))

    def release_device(self, device_id: str, context=None) -> None:
        self.released.append((device_id, context))

    async def release_device_async(self, device_id: str, context=None) -> None:
        self.released.append((device_id, context))


def _patch_task_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_module, "create_trace_id", lambda: "trace-test")
    monkeypatch.setattr(trace_module, "write_replay_task_start", lambda **kwargs: None)
    monkeypatch.setattr(trace_module, "write_replay_event", lambda **kwargs: None)
    monkeypatch.setattr(
        trace_module,
        "get_step_timing_summary",
        lambda step, trace_id=None: {"step": step},
    )
    monkeypatch.setattr(trace_module, "list_step_timing_summaries", lambda trace_id: [])
    monkeypatch.setattr(trace_module, "get_trace_timing_summary", lambda **kwargs: None)
    monkeypatch.setattr(trace_module, "clear_trace_data", lambda trace_id: None)
    monkeypatch.setattr(
        "AutoGLM_GUI.task_manager.record_trace_latency_metrics",
        lambda **kwargs: None,
    )


def test_phone_agent_manager_lifecycle_state_and_abort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PhoneAgentManager()
    fake_agent = FakeAgent()

    class FakeDeviceManager:
        refreshed = False

        def get_device_protocol(self, device_id: str):
            return SimpleNamespace(device_id=device_id)

        def get_async_device_protocol(self, device_id: str):
            return self.get_device_protocol(device_id)

        def force_refresh(self) -> None:
            self.refreshed = True

    monkeypatch.setattr(
        device_manager_module.DeviceManager,
        "get_instance",
        classmethod(lambda cls: FakeDeviceManager()),
    )
    monkeypatch.setattr(
        agents_module,
        "create_agent",
        lambda **kwargs: fake_agent,
    )

    created = manager.initialize_agent_with_factory(
        "device-1",
        "custom",
        ModelConfig(),
        AgentConfig(device_id="actual-1"),
        {},
    )
    assert created is fake_agent
    assert (
        manager.initialize_agent_with_factory(
            "device-1",
            "custom",
            ModelConfig(),
            AgentConfig(device_id="actual-1"),
            {},
        )
        is fake_agent
    )
    assert manager.is_initialized("device-1")
    assert manager.get_agent("device-1") is fake_agent
    assert manager.get_agent_safe("device-1") is fake_agent
    assert manager.get_config("device-1")[0].model_name == "autoglm-phone-9b"
    assert manager.list_agents() == ["device-1"]

    manager.reset_agent("device-1")
    assert fake_agent.reset_count == 1
    assert manager.acquire_device("device-1")
    assert manager.get_state("device-1") == AgentState.BUSY
    assert manager.acquire_device("device-1", raise_on_timeout=False) is False
    with pytest.raises(DeviceBusyError):
        manager.acquire_device("device-1")
    manager.release_device("device-1")
    assert manager.get_state("device-1") == AgentState.IDLE

    with manager.use_agent("device-1", auto_initialize=False) as used:
        assert used is fake_agent
    assert manager.get_state("device-1") == AgentState.IDLE

    event = threading.Event()
    manager.register_abort_handler("device-1", event)
    assert manager.is_streaming_active("device-1")
    assert asyncio.run(manager.abort_streaming_chat_async("device-1")) is True
    assert event.is_set()
    manager.unregister_abort_handler("device-1")
    assert not manager.is_streaming_active("device-1")

    called: list[str] = []
    manager.register_abort_handler("device-1", lambda: called.append("sync"))
    assert asyncio.run(manager.abort_streaming_chat_async("device-1")) is True
    assert called == ["sync"]

    async_called: list[str] = []

    async def async_abort() -> None:
        async_called.append("async")

    manager.register_abort_handler("device-1", async_abort)
    assert asyncio.run(manager.abort_streaming_chat_async("device-1")) is True
    assert async_called == ["async"]

    manager.set_error_state("device-1", "boom")
    assert manager.get_metadata("device-1").error_message == "boom"
    assert manager.get_metadata_for_device("device-1").state == AgentState.ERROR
    assert manager.abort_streaming_chat_async

    manager.destroy_agent("device-1")
    assert not manager.is_initialized("device-1")
    with pytest.raises(AgentNotInitializedError):
        manager.reset_agent("device-1")
    with pytest.raises(AgentNotInitializedError):
        manager.get_config("device-1")


def test_phone_agent_manager_auto_init_errors_and_destroy_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PhoneAgentManager()

    with pytest.raises(AgentInitializationError, match="device_id"):
        manager.initialize_agent_with_factory(
            "device-1", "custom", ModelConfig(), AgentConfig(), {}
        )

    class MissingDeviceManager:
        def __init__(self) -> None:
            self.calls = 0

        def get_device_protocol(self, device_id: str):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("missing")
            return SimpleNamespace(device_id=device_id)

        def get_async_device_protocol(self, device_id: str):
            return self.get_device_protocol(device_id)

        def force_refresh(self) -> None:
            self.refreshed = True

    monkeypatch.setattr(
        device_manager_module.DeviceManager,
        "get_instance",
        classmethod(lambda cls: MissingDeviceManager()),
    )
    monkeypatch.setattr(agents_module, "create_agent", lambda **kwargs: FakeAgent())
    agent = manager.initialize_agent_with_factory(
        "device-2", "custom", ModelConfig(), AgentConfig(device_id="actual-2"), {}
    )
    assert isinstance(agent, FakeAgent)

    class EffectiveConfig:
        base_url = ""
        api_key = "EMPTY"
        model_name = "m"
        agent_type = "custom"
        agent_config_params = {}

    fake_config = SimpleNamespace(
        load_file_config=lambda: None,
        sync_to_env=lambda: None,
        get_effective_config=lambda: EffectiveConfig(),
    )
    monkeypatch.setattr(config_manager_module, "config_manager", fake_config)
    with pytest.raises(AgentInitializationError, match="base_url"):
        manager.get_agent_with_context("device-3", context="chat:s1")

    manager._agents["bad"] = SimpleNamespace(
        reset=lambda: (_ for _ in ()).throw(RuntimeError("reset"))
    )
    manager._metadata["bad"] = AgentMetadata(
        device_id="bad",
        state=AgentState.IDLE,
        model_config=ModelConfig(),
        agent_config=AgentConfig(),
    )
    assert manager.destroy_all_agents() >= 1


def test_task_manager_queue_cancel_worker_and_layered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskStore(tmp_path / "tasks.db")
    manager = TaskManager(store)
    ensured: list[str] = []
    monkeypatch.setattr(
        manager, "_ensure_worker", lambda device_id: ensured.append(device_id)
    )

    running = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-1",
        device_serial="serial-1",
        input_text="running",
        status=TaskStatus.RUNNING.value,
    )
    queued = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-2",
        device_serial="serial-2",
        input_text="queued",
    )
    asyncio.run(manager.start())
    assert store.get_task(running["id"])["status"] == TaskStatus.INTERRUPTED.value

    session = asyncio.run(
        manager.create_chat_session(
            device_id="device-1", device_serial="serial-1", mode="classic"
        )
    )
    submitted = asyncio.run(
        manager.submit_chat_task(
            session_id=session["id"],
            device_id="device-1",
            device_serial="serial-1",
            message="hello",
            attachments=[
                {"mime_type": "image/png", "data": "abc"},
                {"mime_type": 1, "data": "bad"},
            ],
        )
    )
    assert ensured[-1] == "device-1"
    assert manager._get_task_user_image_attachments(submitted["id"]) == [
        {"mime_type": "image/png", "data": "abc"}
    ]
    assert asyncio.run(manager.get_session(session["id"]))["id"] == session["id"]
    assert (
        asyncio.run(
            manager.get_or_create_legacy_chat_session(
                device_id="device-1", device_serial="serial-1", mode="classic"
            )
        )["id"]
        == session["id"]
    )
    assert asyncio.run(manager.archive_session("missing")) is None

    cancelled = asyncio.run(manager.cancel_task(queued["id"]))
    assert cancelled["status"] == TaskStatus.CANCELLED.value
    assert asyncio.run(manager.cancel_task("missing")) is None
    assert asyncio.run(manager.wait_for_task("missing")) is None

    abort_called: list[str] = []
    running_task = store.create_task_run(
        source="chat",
        executor_key="classic_chat",
        device_id="device-1",
        device_serial="serial-1",
        input_text="running",
        status=TaskStatus.RUNNING.value,
    )
    manager._abort_handlers[running_task["id"]] = lambda: abort_called.append("abort")
    asyncio.run(manager.cancel_task(running_task["id"]))
    assert abort_called == ["abort"]

    unsupported = store.create_task_run(
        source="chat",
        executor_key="missing",
        device_id="device-9",
        device_serial="serial-9",
        input_text="bad",
    )
    monkeypatch.setattr(manager, "_ensure_worker", lambda device_id: None)
    asyncio.run(manager._device_worker("device-9"))
    assert store.get_task(unsupported["id"])["status"] == TaskStatus.FAILED.value

    class FakeLayeredRun:
        final_output = ""

        def cancel(self) -> None:
            self.cancelled = True

        async def stream_events(self):
            yield {"type": "tool_result", "payload": {"steps": 2}}
            yield {
                "type": "done",
                "payload": {"content": "layered done", "success": True},
            }

    reset_calls: list[str] = []
    monkeypatch.setattr(
        layered_agent_service, "start_run", lambda **kwargs: FakeLayeredRun()
    )
    monkeypatch.setattr(
        layered_agent_service,
        "reset_session",
        lambda session_id: reset_calls.append(session_id),
    )
    monkeypatch.setattr(trace_module, "write_replay_task_start", lambda **kwargs: None)
    monkeypatch.setattr(trace_module, "write_replay_event", lambda **kwargs: None)
    monkeypatch.setattr(trace_module, "list_step_timing_summaries", lambda trace_id: [])
    monkeypatch.setattr(trace_module, "get_trace_timing_summary", lambda **kwargs: None)
    monkeypatch.setattr(trace_module, "clear_trace_data", lambda trace_id: None)

    layered_task = store.create_task_run(
        source="scheduled",
        executor_key="scheduled_layered_workflow",
        device_id="device-1",
        device_serial="serial-1",
        input_text="layered",
    )
    asyncio.run(manager._execute_scheduled_layered_workflow(layered_task))
    assert store.get_task(layered_task["id"])["status"] == TaskStatus.SUCCEEDED.value
    assert reset_calls == [layered_task["id"]]
    store.close()


def test_task_manager_classic_chat_execution_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_task_tracing(monkeypatch)
    store = TaskStore(tmp_path / "classic.db")
    manager = TaskManager(store)
    monkeypatch.setattr(manager, "_ensure_worker", lambda device_id: None)

    fake_agent = FakeAgent()
    fake_phone_manager = FakePhoneAgentManager(fake_agent)
    monkeypatch.setattr(
        PhoneAgentManager,
        "get_instance",
        classmethod(lambda cls: fake_phone_manager),
    )

    session = asyncio.run(
        manager.create_chat_session(
            device_id="device-1", device_serial="serial-1", mode="classic"
        )
    )
    queued_task = asyncio.run(
        manager.submit_chat_task(
            session_id=session["id"],
            device_id="device-1",
            device_serial="serial-1",
            message="classic task",
            attachments=[
                {"mime_type": "image/png", "data": "image"},
                {"mime_type": 123, "data": "ignored"},
            ],
        )
    )
    task = store.get_task(queued_task["id"])
    assert task is not None

    asyncio.run(manager._execute_classic_chat(task))

    completed = store.get_task(task["id"])
    assert completed is not None
    assert completed["status"] == TaskStatus.SUCCEEDED.value
    assert completed["final_message"] == "done classic task"
    assert completed["step_count"] == 1
    assert fake_agent.attachments == [{"mime_type": "image/png", "data": "image"}]
    assert fake_phone_manager.released == [("device-1", f"chat:{session['id']}")]
    assert fake_phone_manager.unregistered == [("device-1", f"chat:{session['id']}")]
    event_types = [event["event_type"] for event in store.list_task_events(task["id"])]
    assert "thinking" in event_types
    assert "step" in event_types
    assert "done" in event_types

    no_attachment_agent = SimpleNamespace(cancel=lambda: None)

    async def unused_stream(text: str, *, continue_with: str | None = None):
        raise AssertionError("stream should not run")
        yield {}

    no_attachment_agent.stream = unused_stream
    fake_phone_manager.agent = no_attachment_agent
    unsupported = asyncio.run(
        manager.submit_chat_task(
            session_id=session["id"],
            device_id="device-1",
            device_serial="serial-1",
            message="with image",
            attachments=[{"mime_type": "image/png", "data": "image"}],
        )
    )
    unsupported_task = store.get_task(unsupported["id"])
    assert unsupported_task is not None

    asyncio.run(manager._execute_classic_chat(unsupported_task))

    failed = store.get_task(unsupported["id"])
    assert failed is not None
    assert failed["status"] == TaskStatus.FAILED.value
    assert failed["stop_reason"] == "unsupported_image_attachments"
    assert fake_phone_manager.errors[-1][1] == (
        "Current agent does not support user image attachments"
    )
    store.close()


def test_task_manager_classic_chat_resumes_takeover_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_task_tracing(monkeypatch)
    store = TaskStore(tmp_path / "takeover.db")
    manager = TaskManager(store)
    monkeypatch.setattr(manager, "_ensure_worker", lambda device_id: None)

    fake_agent = TakeoverResumeAgent()
    fake_phone_manager = FakePhoneAgentManager(fake_agent)
    monkeypatch.setattr(
        PhoneAgentManager,
        "get_instance",
        classmethod(lambda cls: fake_phone_manager),
    )

    session = asyncio.run(
        manager.create_chat_session(
            device_id="device-1", device_serial="serial-1", mode="classic"
        )
    )
    takeover_task = asyncio.run(
        manager.submit_chat_task(
            session_id=session["id"],
            device_id="device-1",
            device_serial="serial-1",
            message="打开飞书",
        )
    )
    takeover_task = store.get_task(takeover_task["id"])
    assert takeover_task is not None

    asyncio.run(manager._execute_classic_chat(takeover_task))

    completed_takeover = store.get_task(takeover_task["id"])
    assert completed_takeover is not None
    assert completed_takeover["status"] == TaskStatus.SUCCEEDED.value
    assert completed_takeover["stop_reason"] == "takeover"
    assert completed_takeover["step_count"] == 1
    assert manager._takeover_sessions == {session["id"]: True}
    assert fake_agent.stream_calls == [("打开飞书", None)]
    assert [
        event["event_type"] for event in store.list_task_events(takeover_task["id"])
    ].count("takeover") == 1

    continue_task = asyncio.run(
        manager.submit_chat_task(
            session_id=session["id"],
            device_id="device-1",
            device_serial="serial-1",
            message="已完成登录",
        )
    )
    continue_task = store.get_task(continue_task["id"])
    assert continue_task is not None

    asyncio.run(manager._execute_classic_chat(continue_task))

    completed_continue = store.get_task(continue_task["id"])
    assert completed_continue is not None
    assert completed_continue["status"] == TaskStatus.SUCCEEDED.value
    assert completed_continue["final_message"] == "done 已完成登录"
    assert completed_continue["stop_reason"] == "completed"
    assert completed_continue["step_count"] == 2
    assert manager._takeover_sessions == {}
    assert fake_agent.stream_calls == [
        ("打开飞书", None),
        ("已完成登录", "已完成登录"),
    ]
    assert fake_phone_manager.errors == []
    store.close()


def test_task_manager_scheduled_workflow_success_cancel_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_task_tracing(monkeypatch)
    store = TaskStore(tmp_path / "scheduled.db")
    manager = TaskManager(store)
    monkeypatch.setattr(manager, "_ensure_worker", lambda device_id: None)

    fake_agent = FakeAgent()
    fake_phone_manager = FakePhoneAgentManager(fake_agent)
    monkeypatch.setattr(
        PhoneAgentManager,
        "get_instance",
        classmethod(lambda cls: fake_phone_manager),
    )

    scheduled = asyncio.run(
        manager.enqueue_scheduled_task(
            scheduled_task_id="sched-1",
            workflow_uuid="workflow-1",
            schedule_fire_id="fire-1",
            device_id="device-1",
            device_serial="serial-1",
            input_text="scheduled task",
        )
    )
    task = store.get_task(scheduled["id"])
    assert task is not None

    asyncio.run(manager._execute_scheduled_workflow(task))

    completed = store.get_task(task["id"])
    assert completed is not None
    assert completed["status"] == TaskStatus.SUCCEEDED.value
    assert completed["final_message"] == "done scheduled task"
    assert fake_agent.reset_count == 1
    assert fake_phone_manager.released == [("device-1", "scheduled")]

    cancel_task = store.create_task_run(
        source="scheduled",
        executor_key="scheduled_workflow",
        device_id="device-1",
        device_serial="serial-1",
        input_text="cancel me",
    )
    manager._cancel_requested.add(cancel_task["id"])
    asyncio.run(manager._execute_scheduled_workflow(cancel_task))
    cancelled = store.get_task(cancel_task["id"])
    assert cancelled is not None
    assert cancelled["status"] == TaskStatus.CANCELLED.value
    assert cancelled["stop_reason"] == "user_stopped"

    class BusyManager(FakePhoneAgentManager):
        async def acquire_device_async(self, *args, **kwargs) -> bool:
            raise DeviceBusyError("busy")

    busy_manager = BusyManager(fake_agent)
    monkeypatch.setattr(
        PhoneAgentManager,
        "get_instance",
        classmethod(lambda cls: busy_manager),
    )
    busy_task = store.create_task_run(
        source="scheduled",
        executor_key="scheduled_workflow",
        device_id="device-busy",
        device_serial="serial-busy",
        input_text="busy",
    )
    asyncio.run(manager._execute_scheduled_workflow(busy_task))
    busy = store.get_task(busy_task["id"])
    assert busy is not None
    assert busy["status"] == TaskStatus.FAILED.value
    assert busy["stop_reason"] == "device_busy"
    assert busy_manager.errors[-1] == (
        "device-busy",
        "Device device-busy is busy. Please wait.",
        "scheduled",
    )

    class InitErrorManager(FakePhoneAgentManager):
        def get_agent_with_context(self, device_id: str, **kwargs):
            raise AgentInitializationError("missing config")

    init_manager = InitErrorManager(fake_agent)
    monkeypatch.setattr(
        PhoneAgentManager,
        "get_instance",
        classmethod(lambda cls: init_manager),
    )
    init_task = store.create_task_run(
        source="scheduled",
        executor_key="scheduled_workflow",
        device_id="device-init",
        device_serial="serial-init",
        input_text="init",
    )
    asyncio.run(manager._execute_scheduled_workflow(init_task))
    init_failed = store.get_task(init_task["id"])
    assert init_failed is not None
    assert init_failed["status"] == TaskStatus.FAILED.value
    assert init_failed["stop_reason"] == "initialization_failed"
    assert "missing config" in init_failed["final_message"]
    store.close()


def test_mock_and_remote_devices() -> None:
    class StateMachine:
        def __init__(self) -> None:
            self.current_state = SimpleNamespace(current_app="app")
            self.taps: list[tuple[int, int]] = []
            self.swipes: list[tuple[int, int, int, int]] = []

        def get_current_screenshot(self):
            return SimpleNamespace(base64_data="img", width=10, height=20)

        def handle_tap(self, x: int, y: int) -> None:
            self.taps.append((x, y))

        def handle_swipe(self, sx: int, sy: int, ex: int, ey: int) -> None:
            self.swipes.append((sx, sy, ex, ey))

    sm = StateMachine()
    mock = MockDevice("mock-1", sm)
    assert mock.device_id == "mock-1"
    assert mock.state_machine is sm
    assert mock.get_screenshot().width == 10
    mock.tap(1, 2)
    mock.double_tap(3, 4)
    mock.long_press(5, 6)
    mock.swipe(1, 2, 3, 4)
    mock.type_text("x")
    mock.clear_text()
    mock.back()
    mock.home()
    assert mock.launch_app("app")
    assert mock.get_current_app() == "app"
    assert mock.detect_and_set_adb_keyboard() == "com.mock.keyboard"
    mock.restore_keyboard("ime")
    assert sm.taps == [(1, 2), (3, 4), (5, 6)]
    assert sm.swipes == [(1, 2, 3, 4)]

    mock_manager = MockDeviceManager(sm, "mock-1")
    assert mock_manager.list_devices()[0].model == "MockPhone"
    assert mock_manager.get_device("mock-1").device_id == "mock-1"
    with pytest.raises(KeyError):
        mock_manager.get_device("missing")
    assert mock_manager.connect("addr")[0]
    assert mock_manager.disconnect("mock-1")[0]

    class FakeResponse:
        status_code = 200

        def __init__(self, payload: Any) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            pass

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, timeout: float = 30.0) -> None:
            self.calls: list[tuple[str, str, Any]] = []
            self.closed = False

        def post(self, url: str, json=None):
            self.calls.append(("post", url, json))
            if url.endswith("/screenshot"):
                return FakeResponse({"base64_data": "img", "width": 1, "height": 2})
            if url.endswith("/launch_app"):
                return FakeResponse({"success": False})
            if url.endswith("/connect"):
                return FakeResponse({"success": True, "message": "connected"})
            if url.endswith("/disconnect"):
                return FakeResponse({"success": True, "message": "disconnected"})
            if url.endswith("/detect_keyboard"):
                return FakeResponse({"original_ime": "ime"})
            return FakeResponse({})

        def get(self, url: str):
            self.calls.append(("get", url, None))
            if url.endswith("/devices"):
                return FakeResponse(
                    [
                        {
                            "device_id": "dev",
                            "status": "online",
                            "model": "Phone",
                        }
                    ]
                )
            return FakeResponse({"app_name": "app"})

        def close(self) -> None:
            self.closed = True

    import AutoGLM_GUI.devices.remote_device as remote_module

    remote_module.httpx.Client = FakeClient
    remote = RemoteDevice("dev", "http://server/")
    assert remote.device_id == "dev"
    assert remote.get_screenshot().height == 2
    remote.tap(1, 2)
    remote.double_tap(1, 2)
    remote.long_press(1, 2)
    remote.swipe(1, 2, 3, 4)
    remote.type_text("hi")
    remote.clear_text()
    remote.back()
    remote.home()
    assert remote.launch_app("Missing") is False
    assert remote.get_current_app() == "app"
    assert remote.detect_and_set_adb_keyboard() == "ime"
    remote.restore_keyboard("ime")
    with remote:
        pass
    assert remote._client.closed

    remote_manager = RemoteDeviceManager("http://server/")
    assert remote_manager.list_devices()[0].device_id == "dev"
    assert remote_manager.get_device("dev") is remote_manager.get_device("dev")
    assert remote_manager.connect("addr") == (True, "connected")
    assert remote_manager.disconnect("dev") == (True, "disconnected")
    remote_manager.close()


def test_agent_factory_and_adb_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_registry = factory.AGENT_REGISTRY.copy()
    try:
        factory.AGENT_REGISTRY.clear()
        factory.register_agent("custom", lambda **kwargs: "agent")
        factory.register_agent("custom", lambda **kwargs: "agent2")
        assert factory.list_agent_types() == ["custom"]
        assert factory.is_agent_type_registered("custom")
        assert (
            factory.create_agent(
                "custom",
                ModelConfig(),
                AgentConfig(),
                {},
                SimpleNamespace(),
            )
            == "agent2"
        )
        with pytest.raises(ValueError, match="Unknown agent type"):
            factory.create_agent(
                "missing", ModelConfig(), AgentConfig(), {}, SimpleNamespace()
            )

        def bad_creator(**kwargs):
            raise RuntimeError("bad")

        factory.register_agent("bad", bad_creator)
        with pytest.raises(RuntimeError, match="bad"):
            factory.create_agent(
                "bad", ModelConfig(), AgentConfig(), {}, SimpleNamespace()
            )
    finally:
        factory.AGENT_REGISTRY.clear()
        factory.AGENT_REGISTRY.update(original_registry)

    monkeypatch.setattr(adb_manager.shutil, "which", lambda name: "/usr/bin/adb")
    assert adb_manager.ensure_adb() == "/usr/bin/adb"

    platform_tools = tmp_path / "platform-tools"
    cached_adb = platform_tools / "adb"
    cached_adb.parent.mkdir()
    cached_adb.write_text("adb", encoding="utf-8")
    monkeypatch.setattr(adb_manager.shutil, "which", lambda name: None)
    monkeypatch.setattr(adb_manager, "_PLATFORM_TOOLS_DIR", platform_tools)
    monkeypatch.setattr(adb_manager, "_ADB_BINARY", "adb")
    assert adb_manager.ensure_adb() == str(cached_adb)

    cached_adb.unlink()
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("platform-tools/adb", "adb")
    monkeypatch.setattr(
        adb_manager, "_download_with_progress", lambda url: data.getvalue()
    )
    monkeypatch.setattr(adb_manager, "_platform_name", lambda: "linux")
    assert adb_manager.ensure_adb() == str(cached_adb)
    assert cached_adb.stat().st_mode & stat.S_IXUSR

    monkeypatch.setattr(
        adb_manager,
        "_download_with_progress",
        lambda url: (_ for _ in ()).throw(RuntimeError("net")),
    )
    cached_adb.unlink()
    with pytest.raises(RuntimeError, match="Failed to download"):
        adb_manager.ensure_adb()
