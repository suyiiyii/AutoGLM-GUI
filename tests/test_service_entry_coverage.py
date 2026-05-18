"""Coverage for service orchestration, actions, config, and CLI entry paths."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import AutoGLM_GUI.__main__ as main_module
import AutoGLM_GUI.actions.handler as action_handler_module
import AutoGLM_GUI.adb_manager as adb_manager
import AutoGLM_GUI.config_manager as config_manager_module
import AutoGLM_GUI.device_manager as device_manager_module
from AutoGLM_GUI.actions import ActionHandler
from AutoGLM_GUI.config_manager import ConfigModel, ConfigSource, UnifiedConfigManager
from AutoGLM_GUI.models.scheduled_task import ScheduledTask
from AutoGLM_GUI.scheduler_manager import SchedulerManager


class FakeActionDevice:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.launch_success = True
        self.original_ime = "latin/.Ime"

    def launch_app(self, app: str) -> bool:
        self.calls.append(("launch_app", (app,)))
        return self.launch_success

    def tap(self, x: int, y: int) -> None:
        self.calls.append(("tap", (x, y)))

    def detect_and_set_adb_keyboard(self) -> str:
        self.calls.append(("detect_and_set_adb_keyboard", ()))
        return self.original_ime

    def clear_text(self) -> None:
        self.calls.append(("clear_text", ()))

    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", (text,)))

    def restore_keyboard(self, ime: str) -> None:
        self.calls.append(("restore_keyboard", (ime,)))

    def swipe(self, sx: int, sy: int, ex: int, ey: int) -> None:
        self.calls.append(("swipe", (sx, sy, ex, ey)))

    def back(self) -> None:
        self.calls.append(("back", ()))

    def home(self) -> None:
        self.calls.append(("home", ()))

    def double_tap(self, x: int, y: int) -> None:
        self.calls.append(("double_tap", (x, y)))

    def long_press(self, x: int, y: int) -> None:
        self.calls.append(("long_press", (x, y)))


def test_action_handler_covers_supported_and_error_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(action_handler_module, "trace_sleep", lambda *a, **k: None)
    device = FakeActionDevice()
    confirmations: list[str] = []
    takeovers: list[str] = []
    handler = ActionHandler(
        device,
        confirmation_callback=lambda message: confirmations.append(message) or True,
        takeover_callback=lambda message: takeovers.append(message),
    )

    assert handler.execute(
        {"_metadata": "finish", "message": "done"}, 100, 200
    ).should_finish
    assert (
        handler.execute({"_metadata": "bad"}, 100, 200).message
        == "Unknown action type: bad"
    )
    assert (
        handler.execute({"_metadata": "do"}, 100, 200).message == "Unknown action: None"
    )
    assert (
        handler.execute({"_metadata": "do", "action": "Nope"}, 100, 200).message
        == "Unknown action: Nope"
    )

    assert handler.execute(
        {"_metadata": "do", "action": "Launch", "app": "Settings"}, 100, 200
    ).success
    device.launch_success = False
    assert (
        "App not found"
        in handler.execute(
            {"_metadata": "do", "action": "Launch", "app": "Missing"}, 100, 200
        ).message
    )
    assert (
        handler.execute({"_metadata": "do", "action": "Launch"}, 100, 200).message
        == "No app name specified"
    )

    assert handler.execute(
        {
            "_metadata": "do",
            "action": "Tap",
            "element": [500, 1000],
            "message": "confirm",
        },
        100,
        200,
    ).success
    assert confirmations == ["confirm"]
    cancelling = ActionHandler(device, confirmation_callback=lambda _: False)
    assert cancelling.execute(
        {"_metadata": "do", "action": "Tap", "element": [1, 1], "message": "no"},
        100,
        200,
    ).should_finish
    assert (
        handler.execute({"_metadata": "do", "action": "Tap"}, 100, 200).message
        == "No element coordinates"
    )

    assert handler.execute(
        {"_metadata": "do", "action": "Type", "text": "hello"}, 100, 200
    ).success
    device.original_ime = handler._ADB_IME
    assert handler.execute(
        {"_metadata": "do", "action": "Type_Name", "text": "x"}, 100, 200
    ).success
    assert handler.execute(
        {"_metadata": "do", "action": "Swipe", "start": [0, 0], "end": [1000, 1000]},
        100,
        200,
    ).success
    assert (
        handler.execute({"_metadata": "do", "action": "Swipe"}, 100, 200).message
        == "Missing swipe coordinates"
    )
    assert handler.execute({"_metadata": "do", "action": "Back"}, 100, 200).success
    assert handler.execute({"_metadata": "do", "action": "Home"}, 100, 200).success
    assert handler.execute(
        {"_metadata": "do", "action": "Double Tap", "element": [200, 300]}, 100, 200
    ).success
    assert (
        handler.execute({"_metadata": "do", "action": "Double Tap"}, 100, 200).message
        == "No element coordinates"
    )
    assert handler.execute(
        {"_metadata": "do", "action": "Long Press", "element": [200, 300]}, 100, 200
    ).success
    assert (
        handler.execute({"_metadata": "do", "action": "Long Press"}, 100, 200).message
        == "No element coordinates"
    )
    assert handler.execute(
        {"_metadata": "do", "action": "Wait", "duration": "not numeric"}, 100, 200
    ).success
    assert handler.execute(
        {"_metadata": "do", "action": "Take_over", "message": "help"}, 100, 200
    ).success
    assert takeovers == ["help"]
    assert handler.execute({"_metadata": "do", "action": "Note"}, 100, 200).success
    assert handler.execute({"_metadata": "do", "action": "Call_API"}, 100, 200).success
    assert (
        handler.execute({"_metadata": "do", "action": "Interact"}, 100, 200).message
        == "User interaction required"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    device.tap = boom
    assert (
        handler.execute(
            {"_metadata": "do", "action": "Tap", "element": [1, 1]}, 100, 200
        ).message
        == "Action failed: boom"
    )


def test_unified_config_manager_layers_conflicts_and_file_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    UnifiedConfigManager._instance = None
    manager = UnifiedConfigManager()
    manager._config_path = tmp_path / "config.json"

    with pytest.raises(ValueError, match="base_url"):
        ConfigModel(base_url="localhost")
    with pytest.raises(ValueError, match="model_name"):
        ConfigModel(model_name=" ")
    with pytest.raises(ValueError, match="decision_base_url"):
        ConfigModel(decision_base_url="bad")

    assert manager.load_file_config() is False
    assert manager.get_config_source() == ConfigSource.DEFAULT
    assert manager.save_file_config(
        "https://file.test/v1",
        "file-model",
        api_key="file-key",
        agent_type="glm",
        default_max_steps=None,
        default_max_steps_set=True,
        layered_max_turns=None,
        layered_max_turns_set=True,
        decision_base_url="https://decision.test/v1",
        decision_model_name="decision",
        decision_api_key="decision-key",
    )
    assert manager.load_file_config(force_reload=True)
    assert manager.get_field_source("base_url") == ConfigSource.FILE
    assert manager.get_effective_config().agent_type == "glm-async"

    monkeypatch.setenv("AUTOGLM_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("AUTOGLM_MODEL_NAME", "env-model")
    monkeypatch.setenv("AUTOGLM_API_KEY", "env-key")
    monkeypatch.setenv("AUTOGLM_DEFAULT_MAX_STEPS", "25")
    monkeypatch.setenv("AUTOGLM_LAYERED_MAX_TURNS", "5")
    monkeypatch.setenv("AUTOGLM_DECISION_BASE_URL", "https://env-decision.test/v1")
    monkeypatch.setenv("AUTOGLM_DECISION_MODEL_NAME", "env-decision")
    monkeypatch.setenv("AUTOGLM_DECISION_API_KEY", "env-decision-key")
    manager.load_env_config()
    manager.set_cli_config(
        base_url="https://cli.test/v1",
        model_name="cli-model",
        api_key="cli-key",
        layered_max_turns=9,
    )

    effective = manager.get_effective_config()
    assert effective.base_url == "https://cli.test/v1"
    assert effective.model_name == "cli-model"
    assert effective.default_max_steps == 25
    conflicts = manager.detect_conflicts()
    assert {conflict.field for conflict in conflicts} == {
        "base_url",
        "model_name",
        "api_key",
    }
    manager.sync_to_env()
    assert manager.to_dict()["layered_max_turns"] == 9
    assert manager.delete_file_config() is True
    assert manager.delete_file_config() is True

    manager._config_path.write_text("{bad", encoding="utf-8")
    assert manager.load_file_config(force_reload=True) is False
    manager._cli_layer = config_manager_module.ConfigLayer(source=ConfigSource.CLI)
    manager._env_layer = config_manager_module.ConfigLayer(source=ConfigSource.ENV)
    manager._file_layer.base_url = "bad"
    manager._file_layer.explicit_keys = {"base_url"}
    manager._effective_config = None
    assert manager.get_effective_config().base_url == ""

    UnifiedConfigManager._instance = None


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, Any] = {}
        self.started = False
        self.shutdown_called = False

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = False) -> None:
        self.shutdown_called = wait is False

    def add_job(self, func, trigger, id, args, replace_existing):
        self.jobs[id] = SimpleNamespace(
            func=func,
            trigger=trigger,
            args=args,
            next_run_time=datetime(2026, 1, 1),
        )

    def get_job(self, task_id: str):
        return self.jobs.get(task_id)

    def remove_job(self, task_id: str) -> None:
        self.jobs.pop(task_id, None)


@pytest.fixture
def scheduler(tmp_path: Path) -> SchedulerManager:
    SchedulerManager._instance = None
    manager = SchedulerManager()
    manager._tasks_path = tmp_path / "scheduled_tasks.json"
    manager._scheduler = FakeScheduler()
    manager._tasks = {}
    yield manager
    SchedulerManager._instance = None


def test_scheduler_crud_persistence_jobs_and_resolution(
    scheduler: SchedulerManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = scheduler.create_task(
        "Morning",
        "wf-1",
        ["serial-1"],
        "0 8 * * *",
        enabled=True,
        execution_mode="classic",
    )
    assert task.id in scheduler._scheduler.jobs
    assert scheduler.get_task(task.id) is task
    assert scheduler.list_tasks() == [task]
    assert scheduler.get_next_run_time(task.id) == datetime(2026, 1, 1)

    scheduler.update_task(task.id, enabled=False)
    assert task.id not in scheduler._scheduler.jobs
    scheduler.set_enabled(task.id, True)
    assert task.id in scheduler._scheduler.jobs
    scheduler.update_task(task.id, cron_expression="5 9 * * *")
    assert task.id in scheduler._scheduler.jobs
    assert scheduler.set_enabled("missing", True) is False
    assert scheduler.update_task("missing", name="x") is None

    scheduler._add_job(
        ScheduledTask(name="Bad", workflow_uuid="wf", cron_expression="bad")
    )
    scheduler._scheduler.get_job = lambda task_id: (_ for _ in ()).throw(
        RuntimeError("job failed")
    )
    scheduler._remove_job(task.id)

    scheduler._save_tasks()
    scheduler._tasks = {}
    scheduler._load_tasks()
    assert list(scheduler._tasks.values())[0].name == "Morning"
    scheduler._tasks_path.write_text("{bad", encoding="utf-8")
    scheduler._load_tasks()

    assert scheduler.delete_task(task.id) is True
    assert scheduler.delete_task(task.id) is False

    class FakeGroupManager:
        @staticmethod
        def get_all_assignments() -> dict[str, str]:
            return {"assigned": "other"}

        @staticmethod
        def get_devices_in_group(group_id: str) -> list[str]:
            return ["grouped"]

    class FakeDeviceManager:
        @staticmethod
        def get_devices():
            return [
                SimpleNamespace(serial="default-1"),
                SimpleNamespace(serial="assigned"),
            ]

    import AutoGLM_GUI.device_group_manager as group_module

    monkeypatch.setattr(group_module, "device_group_manager", FakeGroupManager())
    monkeypatch.setattr(
        device_manager_module.DeviceManager,
        "get_instance",
        classmethod(lambda cls: FakeDeviceManager()),
    )
    assert scheduler._resolve_device_serialnos(
        ScheduledTask(name="Default", workflow_uuid="wf", device_group_id="default")
    ) == ["default-1"]
    assert scheduler._resolve_device_serialnos(
        ScheduledTask(name="Group", workflow_uuid="wf", device_group_id="g")
    ) == ["grouped"]


def test_scheduler_single_device_execution_paths(scheduler: SchedulerManager) -> None:
    online_device = SimpleNamespace(
        serial="serial-1",
        state=SimpleNamespace(value="online"),
        primary_device_id="device-1",
        model="Pixel",
    )

    class FakeDeviceManager:
        @staticmethod
        def get_devices():
            return [online_device]

    class FakeAgent:
        step_count = 1

        def reset(self) -> None:
            self.reset_called = True

        async def stream(self, text):
            yield {
                "type": "step",
                "data": {"thinking": "think", "action": {"action": "Tap"}, "step": 1},
            }
            yield {"type": "done", "data": {"message": "done", "success": True}}

    class FakePhoneManager:
        def __init__(self, acquired: bool = True, fail_stream: bool = False) -> None:
            self.acquired = acquired
            self.fail_stream = fail_stream
            self.released: list[str] = []

        async def acquire_device_async(self, *args, **kwargs):
            return self.acquired

        def get_agent(self, device_id: str):
            if self.fail_stream:
                raise RuntimeError("agent failed")
            return FakeAgent()

        def release_device(self, device_id: str) -> None:
            self.released.append(device_id)

    class FakeHistory:
        def __init__(self) -> None:
            self.records = []

        def add_record(self, serialno, record) -> None:
            self.records.append((serialno, record))

    history = FakeHistory()
    manager = FakePhoneManager()
    result = asyncio.run(
        scheduler._execute_single_device(
            "serial-1",
            {"text": "do it"},
            "Morning",
            manager,
            FakeDeviceManager(),
            history,
        )
    )
    assert result.success is True
    assert result.device_model == "Pixel"
    assert manager.released == ["device-1"]
    assert history.records[0][1].messages[-1].action == {"action": "Tap"}

    busy = asyncio.run(
        scheduler._execute_single_device(
            "serial-1",
            {"text": "do it"},
            "Morning",
            FakePhoneManager(acquired=False),
            FakeDeviceManager(),
            history,
        )
    )
    assert busy.message == "Device busy"

    offline = asyncio.run(
        scheduler._execute_single_device(
            "missing",
            {"text": "do it"},
            "Morning",
            FakePhoneManager(),
            FakeDeviceManager(),
            history,
        )
    )
    assert offline.message == "Device offline"

    failed = asyncio.run(
        scheduler._execute_single_device(
            "serial-1",
            {"text": "do it"},
            "Morning",
            FakePhoneManager(fail_stream=True),
            FakeDeviceManager(),
            history,
        )
    )
    assert failed.success is False
    assert failed.message == "agent failed"


def test_main_entry_success_error_and_browser_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert isinstance(main_module.find_available_port(0, max_attempts=1), int)
    with pytest.raises(RuntimeError):
        main_module.find_available_port(1, max_attempts=0)

    opened: list[str] = []
    monkeypatch.setattr(main_module.time, "sleep", lambda delay: None)
    monkeypatch.setattr(main_module.webbrowser, "open", lambda url: opened.append(url))

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self) -> None:
            self.target()

    monkeypatch.setattr(main_module.threading, "Thread", ImmediateThread)
    main_module.open_browser("0.0.0.0", 1234, use_ssl=True, delay=0)
    assert opened == ["https://127.0.0.1:1234"]

    fake_uvicorn = ModuleType("uvicorn")
    uvicorn_runs: list[dict[str, Any]] = []
    fake_uvicorn.run = lambda app, **kwargs: uvicorn_runs.append({"app": app, **kwargs})
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(adb_manager, "ensure_adb", lambda: "/adb")
    monkeypatch.setattr(
        device_manager_module.DeviceManager,
        "get_instance",
        classmethod(lambda cls, adb_path=None: SimpleNamespace(adb_path=adb_path)),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autoglm-gui",
            "--base-url",
            "https://model.test/v1",
            "--model",
            "m",
            "--apikey",
            "k",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--no-browser",
            "--no-log-file",
            "--layered-max-turns",
            "3",
        ],
    )
    main_module.main()
    assert uvicorn_runs[-1]["port"] == 8765
    assert uvicorn_runs[-1]["host"] == "127.0.0.1"
    assert "API Key" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["autoglm-gui", "--adb-terminal-repl"])
    monkeypatch.setattr(main_module, "adb_terminal_repl_main", lambda: 7)
    with pytest.raises(SystemExit) as exc:
        main_module.main()
    assert exc.value.code == 7

    monkeypatch.setattr(sys, "argv", ["autoglm-gui", "--port", "9999", "--no-browser"])
    monkeypatch.setattr(
        adb_manager, "ensure_adb", lambda: (_ for _ in ()).throw(RuntimeError("no adb"))
    )
    main_module.main()
    assert uvicorn_runs[-1]["port"] == 9999
