"""Additional unit coverage for pure parsing and file-backed managers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from AutoGLM_GUI.agents.mai.parser import MAIParseError, MAIParser
from AutoGLM_GUI.agents.midscene.log_parser import (
    MidsceneLogParser,
    _is_new_log_entry,
    _strip_timestamp,
)
from AutoGLM_GUI.device_group_manager import DeviceGroupManager
from AutoGLM_GUI.history_manager import HistoryManager
from AutoGLM_GUI.models.device_group import DEFAULT_GROUP_ID, DeviceGroup
from AutoGLM_GUI.models.history import (
    ConversationRecord,
    DeviceHistory,
    MessageRecord,
    StepTimingRecord,
    TraceSummaryRecord,
)
from AutoGLM_GUI.workflow_manager import WorkflowManager


def _make_midscene_plan(action_type: str = "Tap") -> str:
    return json.dumps(
        {
            "thought": "tap the button",
            "log": "tap login",
            "action": {"type": action_type, "param": {"x": 1}},
            "shouldContinuePlanning": False,
        }
    )


def test_midscene_log_parser_extracts_debug_events() -> None:
    parser = MidsceneLogParser()

    reasoning = parser.feed(
        "2026-05-19T01:02:03.456Z midscene:ai:call response reasoning content: think"
    )
    action = parser.feed(
        "2026-05-19T01:02:03.456Z midscene:agent:task-builder calling action Tap"
    )
    plan = parser.feed(
        "2026-05-19T01:02:03.456Z midscene:device-task-executor planResult "
        + _make_midscene_plan()
    )

    assert reasoning == [{"event": "reasoning", "data": "think"}]
    assert action == [{"event": "action_executing", "data": "Tap"}]
    assert plan[0]["event"] == "plan_result"
    assert plan[0]["data"]["action"]["type"] == "Tap"


def test_midscene_log_parser_flushes_multiline_json_and_task_messages() -> None:
    parser = MidsceneLogParser()

    assert parser.feed("dbug midscene:device-task-executor planResult {") == []
    assert parser.feed('"thought": "inspect",') == []
    assert parser.feed('"log": "look",') == []
    assert parser.feed('"action": {"type": "Insight"},') == []
    assert parser.feed('"shouldContinuePlanning": true') == []
    plan_events = parser.feed("}")

    assert plan_events[0]["event"] == "plan_result"
    assert plan_events[0]["data"]["thought"] == "inspect"

    assert parser.feed("Task finished, message: first line") == []
    assert parser.feed("second line") == []
    finished = parser.feed("info another log entry")

    assert finished == [{"event": "task_finished", "data": "first line\nsecond line"}]

    parser.feed("Task finished, message: trailing")
    assert parser.flush() == [{"event": "task_finished", "data": "trailing"}]


def test_midscene_log_parser_helpers_and_oversized_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    timestamped = "2026-05-19T01:02:03.456Z content"

    assert _is_new_log_entry(timestamped)
    assert _is_new_log_entry("Action tap")
    assert not _is_new_log_entry("continuation")
    assert _strip_timestamp(timestamped) == "content"
    assert _strip_timestamp("plain") == "plain"

    parser = MidsceneLogParser()
    parser.feed("dbug midscene:device-task-executor planResult {")
    for index in range(201):
        parser.feed(f'"line{index}": "value",')

    assert "JSON block too long" in caplog.text
    assert parser.flush() == []


def _tool_call(arguments: dict[str, object]) -> str:
    return (
        "<thinking>ready</thinking><tool_call>"
        + json.dumps({"name": "mobile_use", "arguments": arguments})
        + "</tool_call>"
    )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            {"action": "click", "coordinate": [0.25, 0.75]},
            {"_metadata": "do", "action": "Tap", "element": [250, 750]},
        ),
        (
            {"action": "long_press", "coordinate": [0.1, 0.2]},
            {"_metadata": "do", "action": "Long Press", "element": [100, 200]},
        ),
        (
            {"action": "double_click", "coordinate": [0.9, 0.8]},
            {"_metadata": "do", "action": "Double Tap", "element": [900, 800]},
        ),
        (
            {"action": "wait"},
            {"_metadata": "do", "action": "Wait", "duration": "1 seconds"},
        ),
        (
            {"action": "system_button", "button": "home"},
            {"_metadata": "do", "action": "Home"},
        ),
        (
            {"action": "system_button", "button": "menu"},
            {"_metadata": "do", "action": "Back"},
        ),
        (
            {"action": "type", "text": "hello"},
            {"_metadata": "do", "action": "Type", "text": "hello"},
        ),
        (
            {"action": "open", "app": "Settings"},
            {"_metadata": "do", "action": "Launch", "app": "Settings"},
        ),
        (
            {"action": "answer", "text": "done"},
            {"_metadata": "finish", "message": "done"},
        ),
        (
            {"action": "terminate", "status": "success"},
            {"_metadata": "finish", "message": "Task completed"},
        ),
        (
            {"action": "terminate", "status": "failed"},
            {"_metadata": "finish", "message": "Task failed"},
        ),
    ],
)
def test_mai_parser_converts_actions(
    arguments: dict[str, object], expected: dict[str, object]
) -> None:
    assert MAIParser().parse(_tool_call(arguments)) == expected


@pytest.mark.parametrize(
    ("direction", "start", "end"),
    [
        ("up", [500, 800], [500, 200]),
        ("down", [500, 200], [500, 800]),
        ("left", [800, 500], [200, 500]),
        ("right", [200, 500], [800, 500]),
        ("diagonal", [500, 500], [500, 500]),
    ],
)
def test_mai_parser_swipe_directions(
    direction: str, start: list[int], end: list[int]
) -> None:
    assert MAIParser().parse(
        _tool_call(
            {"action": "swipe", "direction": direction, "coordinate": [0.5, 0.5]}
        )
    ) == {"_metadata": "do", "action": "Swipe", "start": start, "end": end}


def test_mai_parser_handles_think_alias_drag_and_scaled_coordinates() -> None:
    parser = MAIParser()
    raw = (
        "step one</think><tool_call>"
        + json.dumps(
            {
                "name": "mobile_use",
                "arguments": {"action": "click", "coordinate": [0, 0, 999, 999]},
            }
        )
        + "</tool_call>"
    )

    parsed = parser.parse_with_thinking(raw)
    dragged = parser.parse(
        _tool_call(
            {
                "action": "drag",
                "start_coordinate": [0, 999],
                "end_coordinate": [999, 0],
            }
        )
    )

    assert parsed["thinking"] == "step one"
    assert parsed["raw_action"]["coordinate"] == [0.5, 0.5]
    assert parsed["converted_action"] == {
        "_metadata": "do",
        "action": "Tap",
        "element": [500, 500],
    }
    assert dragged == {
        "_metadata": "do",
        "action": "Swipe",
        "start": [0, 1000],
        "end": [1000, 0],
    }
    assert parser.coordinate_scale == 999


def test_mai_parser_rejects_invalid_content() -> None:
    parser = MAIParser()

    with pytest.raises(ValueError, match="Failed to find"):
        parser.parse("plain text")
    with pytest.raises(ValueError, match="Invalid JSON"):
        parser.parse("<thinking>x</thinking><tool_call>{bad</tool_call>")
    with pytest.raises(ValueError, match="Unknown MAI action type"):
        parser.parse(_tool_call({"action": "unknown"}))
    with pytest.raises(MAIParseError, match="Invalid coordinate format"):
        parser.parse_with_thinking(_tool_call({"action": "click", "coordinate": [1]}))


@pytest.fixture
def workflow_manager(tmp_path: Path) -> WorkflowManager:
    WorkflowManager._instance = None
    manager = WorkflowManager()
    manager._workflows_path = tmp_path / "workflows.json"
    manager._file_cache = None
    manager._file_mtime = None
    yield manager
    WorkflowManager._instance = None


def test_workflow_manager_crud_cache_and_bad_json(
    workflow_manager: WorkflowManager,
) -> None:
    assert workflow_manager.list_workflows() == []

    created = workflow_manager.create_workflow("Morning", "sign in")
    cached = workflow_manager.list_workflows()
    updated = workflow_manager.update_workflow(created["uuid"], "Evening", "sign out")

    assert cached == [created]
    assert updated == {
        "uuid": created["uuid"],
        "name": "Evening",
        "text": "sign out",
    }
    assert workflow_manager.get_workflow(created["uuid"]) == updated
    assert workflow_manager.get_workflow("missing") is None
    assert workflow_manager.update_workflow("missing", "x", "y") is None
    assert workflow_manager.delete_workflow("missing") is False
    assert workflow_manager.delete_workflow(created["uuid"]) is True
    assert workflow_manager.list_workflows() == []

    workflow_manager._workflows_path.write_text("{bad", encoding="utf-8")
    workflow_manager._file_cache = None
    workflow_manager._file_mtime = None
    assert workflow_manager.list_workflows() == []


@pytest.fixture
def device_group_manager(tmp_path: Path) -> DeviceGroupManager:
    DeviceGroupManager._instance = None
    manager = DeviceGroupManager()
    manager._groups_path = tmp_path / "device_groups.json"
    manager._groups_cache = None
    manager._assignments_cache = None
    manager._file_mtime = None
    yield manager
    DeviceGroupManager._instance = None


def test_device_group_manager_crud_assignments_and_cache(
    device_group_manager: DeviceGroupManager,
) -> None:
    groups = device_group_manager.list_groups()
    assert [group.id for group in groups] == [DEFAULT_GROUP_ID]
    assert device_group_manager.delete_group(DEFAULT_GROUP_ID) is False

    work = device_group_manager.create_group("Work")
    personal = device_group_manager.create_group("Personal")
    assert device_group_manager.get_group(work.id).name == "Work"
    assert device_group_manager.update_group(work.id, "Office").name == "Office"
    assert device_group_manager.update_group("missing", "x") is None

    assert device_group_manager.assign_device("serial-1", work.id) is True
    assert device_group_manager.assign_device("serial-2", "missing") is False
    assert device_group_manager.get_device_group("serial-1") == work.id
    assert device_group_manager.get_device_group("unknown") == DEFAULT_GROUP_ID
    assert device_group_manager.get_devices_in_group(work.id) == ["serial-1"]
    assert device_group_manager.get_all_assignments() == {"serial-1": work.id}

    assert device_group_manager.reorder_groups([DEFAULT_GROUP_ID, personal.id, work.id])
    assert device_group_manager.reorder_groups(["missing"]) is False
    assert [group.id for group in device_group_manager.list_groups()] == [
        DEFAULT_GROUP_ID,
        personal.id,
        work.id,
    ]

    assert device_group_manager.delete_group(work.id) is True
    assert device_group_manager.get_device_group("serial-1") == DEFAULT_GROUP_ID
    assert device_group_manager.get_devices_in_group(DEFAULT_GROUP_ID) == ["serial-1"]
    assert device_group_manager.delete_group("missing") is False


def test_device_group_manager_recovers_default_and_bad_json(
    device_group_manager: DeviceGroupManager,
) -> None:
    custom = DeviceGroup(id="custom", name="Custom", order=2)
    device_group_manager._groups_path.parent.mkdir(parents=True, exist_ok=True)
    device_group_manager._groups_path.write_text(
        json.dumps(
            {
                "groups": [custom.to_dict()],
                "device_assignments": {"serial": "custom"},
            }
        ),
        encoding="utf-8",
    )
    device_group_manager._groups_cache = None
    device_group_manager._assignments_cache = None
    device_group_manager._file_mtime = None

    assert [group.id for group in device_group_manager.list_groups()] == [
        DEFAULT_GROUP_ID,
        "custom",
    ]

    device_group_manager._groups_path.write_text("{bad", encoding="utf-8")
    device_group_manager._groups_cache = None
    device_group_manager._assignments_cache = None
    device_group_manager._file_mtime = None
    assert [group.id for group in device_group_manager.list_groups()] == [
        DEFAULT_GROUP_ID
    ]


@pytest.fixture
def history_manager(tmp_path: Path) -> HistoryManager:
    HistoryManager._instance = None
    manager = HistoryManager()
    manager._history_dir = tmp_path / "history"
    manager._file_cache = {}
    manager._file_mtime = {}
    yield manager
    HistoryManager._instance = None


def _conversation(record_id: str = "record-1") -> ConversationRecord:
    return ConversationRecord(
        id=record_id,
        task_text="task",
        final_message="done",
        success=True,
        steps=1,
        source="chat",
        trace_id="trace-1",
        step_timings=[
            StepTimingRecord(step=1, trace_id="trace-1", llm_duration_ms=2.5)
        ],
        trace_summary=TraceSummaryRecord(trace_id="trace-1", steps=1),
        messages=[
            MessageRecord(
                role="assistant",
                content="done",
                thinking="think",
                action={"action": "Tap"},
                step=1,
            )
        ],
    )


def test_history_manager_crud_cache_and_serial_safety(
    history_manager: HistoryManager,
) -> None:
    record = _conversation()

    assert (
        history_manager._sanitize_serialno("")
        == "ad87109bfff0765f4dd8cf4943b04d16a4070fea"
    )
    assert history_manager._sanitize_serialno("../bad") != "../bad"
    assert history_manager._sanitize_serialno("adb-1._tcp:5555") == "adb-1._tcp:5555"

    history_manager.add_record("serial-1", record)
    assert history_manager.get_total_count("serial-1") == 1
    assert history_manager.list_records("serial-1")[0].id == "record-1"
    assert history_manager.list_records("serial-1", limit=1, offset=1) == []
    assert history_manager.get_record("serial-1", "record-1").trace_id == "trace-1"
    assert history_manager.get_record("serial-1", "missing") is None

    loaded_once = history_manager._load_history("serial-1")
    loaded_twice = history_manager._load_history("serial-1")
    assert loaded_once is loaded_twice

    assert history_manager.delete_record("serial-1", "missing") is False
    assert history_manager.delete_record("serial-1", "record-1") is True
    assert history_manager.get_total_count("serial-1") == 0
    assert history_manager.clear_device_history("serial-1") is True
    assert history_manager.clear_device_history("serial-1") is False


def test_history_manager_models_and_corrupt_file(
    history_manager: HistoryManager,
) -> None:
    record = _conversation()
    history = DeviceHistory(serialno="serial-1", records=[record])
    round_tripped = DeviceHistory.from_dict(history.to_dict())

    assert round_tripped.records[0].messages[0].action == {"action": "Tap"}
    assert round_tripped.records[0].step_timings[0].llm_duration_ms == 2.5
    assert round_tripped.records[0].trace_summary.trace_id == "trace-1"

    path = history_manager._get_history_path("serial-2")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad", encoding="utf-8")
    assert history_manager._load_history("serial-2").records == []


def test_history_manager_save_failure_cleans_temp_file(
    history_manager: HistoryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = DeviceHistory(serialno="serial-1", records=[_conversation()])
    real_open = open

    def failing_open(path, *args, **kwargs):
        if str(path).endswith(".tmp"):
            raise OSError("write failed")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", failing_open)

    assert history_manager._save_history(history) is False
    assert (
        not history_manager._get_history_path("serial-1").with_suffix(".tmp").exists()
    )
