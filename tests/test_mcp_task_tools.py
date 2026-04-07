"""Tests for Phase 2: MCP async task scheduling tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import AutoGLM_GUI.api.mcp as mcp_api
from AutoGLM_GUI.task_store import TaskStore


pytestmark = [pytest.mark.contract]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTaskManager:
    """Minimal fake that tracks sessions and tasks in-memory."""

    def __init__(self, store: TaskStore) -> None:
        self._store = store
        self._session_counter = 0

    async def get_or_create_legacy_chat_session(
        self, *, device_id: str, device_serial: str, mode: str = "classic"
    ) -> dict[str, Any]:
        self._session_counter += 1
        session_id = f"session-{self._session_counter}"
        return self._store.create_session(
            kind="chat",
            mode=mode,
            device_id=device_id,
            device_serial=device_serial,
            session_id=session_id,
        )

    async def submit_chat_task(
        self,
        *,
        session_id: str,
        device_id: str,
        device_serial: str,
        message: str,
    ) -> dict[str, Any]:
        return self._store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            session_id=session_id,
            device_id=device_id,
            device_serial=device_serial,
            input_text=message,
        )

    async def cancel_task(self, task_id: str) -> dict[str, Any] | None:
        task = self._store.get_task(task_id)
        if task is None:
            return None
        if task["status"] == "QUEUED":
            return self._store.cancel_queued_task(task_id)
        return task


# ---------------------------------------------------------------------------
# Tests: create_task
# ---------------------------------------------------------------------------


def test_create_task_queues_task(tmp_path: Path) -> None:
    """create_task should create a session and a QUEUED task."""
    store = TaskStore(tmp_path / "tasks.db")
    fake_tm = _FakeTaskManager(store)

    import AutoGLM_GUI.task_manager as tm_mod

    original = tm_mod.task_manager
    tm_mod.task_manager = fake_tm

    try:
        result = asyncio.run(
            mcp_api.create_task(
                device_id="dev-1",
                device_serial="serial-1",
                message="打开微信",
            )
        )

        assert result["status"] == "QUEUED"
        assert result["input_text"] == "打开微信"
        assert "task_id" in result
        assert "session_id" in result

        # Verify task is persisted
        task = store.get_task(result["task_id"])
        assert task is not None
        assert task["device_id"] == "dev-1"
        assert task["device_serial"] == "serial-1"
    finally:
        tm_mod.task_manager = original
        store.close()


def test_create_task_with_layered_mode(tmp_path: Path) -> None:
    """create_task with mode='layered' should create a layered session."""
    store = TaskStore(tmp_path / "tasks.db")
    fake_tm = _FakeTaskManager(store)

    import AutoGLM_GUI.task_manager as tm_mod

    original = tm_mod.task_manager
    tm_mod.task_manager = fake_tm

    try:
        result = asyncio.run(
            mcp_api.create_task(
                device_id="dev-1",
                device_serial="serial-1",
                message="test layered",
                mode="layered",
            )
        )

        assert result["status"] == "QUEUED"

        session = store.get_session(result["session_id"])
        assert session is not None
        assert session["mode"] == "layered"
    finally:
        tm_mod.task_manager = original
        store.close()


# ---------------------------------------------------------------------------
# Tests: get_task
# ---------------------------------------------------------------------------


def test_get_task_returns_task_data(tmp_path: Path) -> None:
    """get_task should return task details including duration_ms."""
    store = TaskStore(tmp_path / "tasks.db")
    original_store = mcp_api.task_store
    mcp_api.task_store = store

    try:
        store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            device_id="dev-1",
            device_serial="serial-1",
            input_text="hello",
            task_id="task-1",
        )

        result = asyncio.run(mcp_api.get_task("task-1"))

        assert result is not None
        assert result["id"] == "task-1"
        assert result["status"] == "QUEUED"
        assert result["device_id"] == "dev-1"
        assert result["device_serial"] == "serial-1"
        assert result["input_text"] == "hello"
        assert result["duration_ms"] is None
    finally:
        mcp_api.task_store = original_store
        store.close()


def test_get_task_returns_none_for_unknown() -> None:
    """get_task should return None for a non-existent task."""

    class _EmptyStore:
        def get_task(self, task_id: str) -> dict[str, Any] | None:
            return None

    original = mcp_api.task_store
    mcp_api.task_store = _EmptyStore()

    try:
        result = asyncio.run(mcp_api.get_task("nonexistent"))
        assert result is None
    finally:
        mcp_api.task_store = original


# ---------------------------------------------------------------------------
# Tests: list_tasks
# ---------------------------------------------------------------------------


def test_list_tasks_returns_empty() -> None:
    """list_tasks with no tasks returns empty list."""

    class _EmptyStore:
        def list_tasks(self, **kwargs: Any) -> tuple[list, int]:
            return [], 0

    original = mcp_api.task_store
    mcp_api.task_store = _EmptyStore()

    try:
        result = asyncio.run(mcp_api.list_tasks())
        assert result["tasks"] == []
        assert result["total"] == 0
    finally:
        mcp_api.task_store = original


def test_list_tasks_with_status_filter(tmp_path: Path) -> None:
    """list_tasks filters by status correctly."""
    store = TaskStore(tmp_path / "tasks.db")
    original = mcp_api.task_store
    mcp_api.task_store = store

    try:
        store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            device_id="dev-1",
            device_serial="s1",
            input_text="task-a",
            task_id="t1",
        )

        # Filter by RUNNING should return 0 (task is QUEUED)
        result = asyncio.run(mcp_api.list_tasks(status="RUNNING"))
        assert result["total"] == 0

        # Filter by QUEUED should return 1
        result = asyncio.run(mcp_api.list_tasks(status="QUEUED"))
        assert result["total"] == 1
        assert result["tasks"][0]["id"] == "t1"
    finally:
        mcp_api.task_store = original
        store.close()


def test_list_tasks_rejects_invalid_status() -> None:
    """list_tasks raises ValueError for invalid status."""
    with pytest.raises(ValueError, match="Invalid status"):
        asyncio.run(mcp_api.list_tasks(status="INVALID"))


def test_list_tasks_clamps_limit_and_offset(tmp_path: Path) -> None:
    """list_tasks clamps limit to [1,100] and offset to >= 0."""
    store = TaskStore(tmp_path / "tasks.db")
    original = mcp_api.task_store
    mcp_api.task_store = store

    try:
        # Create 3 tasks
        for i in range(3):
            store.create_task_run(
                source="chat",
                executor_key="classic_chat",
                device_id="dev-1",
                device_serial="s1",
                input_text=f"task-{i}",
            )

        # limit=0 → clamped to 1
        result = asyncio.run(mcp_api.list_tasks(limit=0))
        assert result["limit"] == 1
        assert len(result["tasks"]) == 1

        # limit=200 → clamped to 100
        result = asyncio.run(mcp_api.list_tasks(limit=200))
        assert result["limit"] == 100
    finally:
        mcp_api.task_store = original
        store.close()


def test_list_tasks_filters_by_device_serial(tmp_path: Path) -> None:
    """list_tasks filters by device_serial."""
    store = TaskStore(tmp_path / "tasks.db")
    original = mcp_api.task_store
    mcp_api.task_store = store

    try:
        store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            device_id="dev-1",
            device_serial="s1",
            input_text="task-a",
        )
        store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            device_id="dev-2",
            device_serial="s2",
            input_text="task-b",
        )

        result = asyncio.run(mcp_api.list_tasks(device_serial="s1"))
        assert result["total"] == 1
        assert result["tasks"][0]["device_serial"] == "s1"
    finally:
        mcp_api.task_store = original
        store.close()


# ---------------------------------------------------------------------------
# Tests: cancel_task
# ---------------------------------------------------------------------------


def test_cancel_task_not_found() -> None:
    """cancel_task returns error for non-existent task."""
    import AutoGLM_GUI.task_manager as tm_mod

    class _FakeTM:
        async def cancel_task(self, task_id: str) -> dict[str, Any] | None:
            return None

    original = tm_mod.task_manager
    tm_mod.task_manager = _FakeTM()

    try:
        result = asyncio.run(mcp_api.cancel_task("nonexistent"))
        assert result["success"] is False
        assert "not found" in result["message"].lower()
    finally:
        tm_mod.task_manager = original


def test_cancel_queued_task(tmp_path: Path) -> None:
    """cancel_task on a QUEUED task should cancel it."""
    store = TaskStore(tmp_path / "tasks.db")
    fake_tm = _FakeTaskManager(store)

    import AutoGLM_GUI.task_manager as tm_mod

    original = tm_mod.task_manager
    tm_mod.task_manager = fake_tm

    try:
        store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            device_id="dev-1",
            device_serial="s1",
            input_text="cancel me",
            task_id="task-to-cancel",
        )

        result = asyncio.run(mcp_api.cancel_task("task-to-cancel"))
        assert result["success"] is True
        assert result["task"]["status"] == "CANCELLED"
    finally:
        tm_mod.task_manager = original
        store.close()


# ---------------------------------------------------------------------------
# Tests: get_task_events
# ---------------------------------------------------------------------------


def test_get_task_events_returns_events(tmp_path: Path) -> None:
    """get_task_events returns all events for a task."""
    store = TaskStore(tmp_path / "tasks.db")
    original = mcp_api.task_store
    mcp_api.task_store = store

    try:
        store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            device_id="dev-1",
            device_serial="s1",
            input_text="hello",
            task_id="t1",
        )

        store.append_event(
            task_id="t1",
            event_type="step",
            payload={"step": 1, "action": "tap"},
            role="assistant",
        )
        store.append_event(
            task_id="t1",
            event_type="done",
            payload={"message": "done", "success": True},
            role="assistant",
        )

        result = asyncio.run(mcp_api.get_task_events("t1"))

        assert result["task_id"] == "t1"
        assert "error" not in result
        # Events: status (auto), step, done
        assert len(result["events"]) == 3

        event_types = [e["event_type"] for e in result["events"]]
        assert "step" in event_types
        assert "done" in event_types
    finally:
        mcp_api.task_store = original
        store.close()


def test_get_task_events_with_after_seq(tmp_path: Path) -> None:
    """get_task_events respects after_seq for polling."""
    store = TaskStore(tmp_path / "tasks.db")
    original = mcp_api.task_store
    mcp_api.task_store = store

    try:
        store.create_task_run(
            source="chat",
            executor_key="classic_chat",
            device_id="dev-1",
            device_serial="s1",
            input_text="hello",
            task_id="t1",
        )
        # Auto-created status event is seq=1
        store.append_event(
            task_id="t1",
            event_type="step",
            payload={"step": 1},
            role="assistant",
        )
        store.append_event(
            task_id="t1",
            event_type="step",
            payload={"step": 2},
            role="assistant",
        )

        # Poll for events after seq 1 (status event)
        result = asyncio.run(mcp_api.get_task_events("t1", after_seq=1))
        assert len(result["events"]) == 2
        assert result["events"][0]["seq"] == 2
        assert result["events"][1]["seq"] == 3
    finally:
        mcp_api.task_store = original
        store.close()


def test_get_task_events_unknown_task() -> None:
    """get_task_events returns error for unknown task."""

    class _EmptyStore:
        def get_task(self, task_id: str) -> dict[str, Any] | None:
            return None

    original = mcp_api.task_store
    mcp_api.task_store = _EmptyStore()

    try:
        result = asyncio.run(mcp_api.get_task_events("nonexistent"))
        assert result["error"] == "Task not found"
        assert result["events"] == []
    finally:
        mcp_api.task_store = original


# ---------------------------------------------------------------------------
# Tests: get_device
# ---------------------------------------------------------------------------


def test_get_device_returns_device_info() -> None:
    """get_device returns device details for a valid device_id."""

    class _FakeManagedDevice:
        serial = "serial-1"
        connection_type = MagicMock(value="usb")

        def to_dict(self) -> dict[str, Any]:
            return {
                "id": "dev-1",
                "serial": "serial-1",
                "model": "Pixel 6",
                "status": "device",
                "connection_type": "usb",
                "state": "online",
                "is_available_only": False,
            }

        @property
        def connections(self) -> list:
            return []

    class _FakeDeviceManager:
        def get_serial_by_device_id(self, device_id: str) -> str | None:
            return "serial-1" if device_id == "dev-1" else None

        def get_device_by_serial(self, serial: str) -> _FakeManagedDevice | None:
            return _FakeManagedDevice() if serial == "serial-1" else None

    class _FakePhoneAgentManager:
        pass

    import AutoGLM_GUI.device_manager as dm_mod
    import AutoGLM_GUI.phone_agent_manager as pam_mod

    orig_dm = dm_mod.DeviceManager
    orig_pam = pam_mod.PhoneAgentManager

    dm_mod.DeviceManager = MagicMock(get_instance=lambda: _FakeDeviceManager())  # type: ignore[attr-defined]
    pam_mod.PhoneAgentManager = MagicMock(get_instance=lambda: _FakePhoneAgentManager())  # type: ignore[attr-defined]

    try:
        result = asyncio.run(mcp_api.get_device("dev-1"))
        assert result is not None
        assert result["id"] == "dev-1"
        assert result["serial"] == "serial-1"
    finally:
        dm_mod.DeviceManager = orig_dm
        pam_mod.PhoneAgentManager = orig_pam


def test_get_device_returns_none_for_unknown() -> None:
    """get_device returns None for an unknown device_id."""

    class _FakeDeviceManager:
        def get_serial_by_device_id(self, device_id: str) -> str | None:
            return None

        def get_device_by_serial(self, serial: str) -> None:
            return None

    import AutoGLM_GUI.device_manager as dm_mod
    import AutoGLM_GUI.phone_agent_manager as pam_mod

    orig_dm = dm_mod.DeviceManager
    orig_pam = pam_mod.PhoneAgentManager

    dm_mod.DeviceManager = MagicMock(get_instance=lambda: _FakeDeviceManager())  # type: ignore[attr-defined]
    pam_mod.PhoneAgentManager = MagicMock(get_instance=lambda: None)  # type: ignore[attr-defined]

    try:
        result = asyncio.run(mcp_api.get_device("unknown"))
        assert result is None
    finally:
        dm_mod.DeviceManager = orig_dm
        pam_mod.PhoneAgentManager = orig_pam
