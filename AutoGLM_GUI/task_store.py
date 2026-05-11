"""SQLite-backed task persistence."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from .trace import current_trace_id, trace_span


def _now_iso() -> str:
    return datetime.now().isoformat()


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class TaskSessionStatus(StrEnum):
    OPEN = "open"
    ARCHIVED = "archived"


TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.INTERRUPTED,
}


TaskRecord = dict[str, Any]
TaskEventRecord = dict[str, Any]
TaskSessionRecord = dict[str, Any]


class TaskStore:
    """Simple thread-safe SQLite task store."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or Path.home() / ".config" / "autoglm" / "tasks.db"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._ensure_ready()

    def _ensure_ready(self) -> None:
        with self._lock:
            if self._conn is not None:
                return

            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._conn = conn
            self._create_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _create_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_sessions (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                mode TEXT NOT NULL,
                device_id TEXT NOT NULL,
                device_serial TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_runs (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                executor_key TEXT NOT NULL,
                session_id TEXT NULL REFERENCES task_sessions(id) ON DELETE SET NULL,
                scheduled_task_id TEXT NULL,
                workflow_uuid TEXT NULL,
                schedule_fire_id TEXT NULL,
                device_id TEXT NOT NULL,
                device_serial TEXT NOT NULL,
                status TEXT NOT NULL,
                input_text TEXT NOT NULL,
                final_message TEXT NULL,
                error_message TEXT NULL,
                stop_reason TEXT NULL,
                trace_id TEXT NULL,
                step_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT NULL,
                finished_at TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                role TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(task_id, seq)
            );

            CREATE INDEX IF NOT EXISTS idx_task_sessions_device
                ON task_sessions(device_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_runs_device_status
                ON task_runs(device_id, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_task_runs_session
                ON task_runs(session_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_runs_serial
                ON task_runs(device_serial, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_runs_source
                ON task_runs(source, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_runs_schedule
                ON task_runs(scheduled_task_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_runs_schedule_fire
                ON task_runs(schedule_fire_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_task_events_task_seq
                ON task_events(task_id, seq);
            """
        )
        columns = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(task_runs)").fetchall()
        }
        if "stop_reason" not in columns:
            self._conn.execute("ALTER TABLE task_runs ADD COLUMN stop_reason TEXT NULL")
        if "trace_id" not in columns:
            self._conn.execute("ALTER TABLE task_runs ADD COLUMN trace_id TEXT NULL")
        self._conn.commit()

    def _fetchone(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        assert self._conn is not None
        return self._conn.execute(query, params).fetchone()

    def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        assert self._conn is not None
        return list(self._conn.execute(query, params).fetchall())

    @staticmethod
    def _row_to_session(row: sqlite3.Row | None) -> TaskSessionRecord | None:
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _row_to_task(row: sqlite3.Row | None) -> TaskRecord | None:
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _row_to_event(row: sqlite3.Row | None) -> TaskEventRecord | None:
        if row is None:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data

    def create_session(
        self,
        *,
        kind: str,
        mode: str,
        device_id: str,
        device_serial: str,
        status: str = TaskSessionStatus.OPEN.value,
        session_id: str | None = None,
    ) -> TaskSessionRecord:
        self._ensure_ready()
        now = _now_iso()
        record_id = session_id or str(uuid4())
        with trace_span(
            "task_store.session.create",
            attrs={
                "session_id": record_id,
                "kind": kind,
                "mode": mode,
                "device_id": device_id,
                "device_serial": device_serial,
                "status": status,
            },
        ):
            with self._lock:
                assert self._conn is not None
                self._conn.execute(
                    """
                    INSERT INTO task_sessions (
                        id, kind, mode, device_id, device_serial, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        kind,
                        mode,
                        device_id,
                        device_serial,
                        status,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
                return self.get_session(record_id) or {}

    def get_session(self, session_id: str) -> TaskSessionRecord | None:
        self._ensure_ready()
        with self._lock:
            return self._row_to_session(
                self._fetchone(
                    "SELECT * FROM task_sessions WHERE id = ?",
                    (session_id,),
                )
            )

    def update_session_timestamp(self, session_id: str) -> None:
        self._ensure_ready()
        with trace_span(
            "task_store.session.touch",
            attrs={"session_id": session_id},
        ):
            with self._lock:
                assert self._conn is not None
                self._conn.execute(
                    "UPDATE task_sessions SET updated_at = ? WHERE id = ?",
                    (_now_iso(), session_id),
                )
                self._conn.commit()

    def get_latest_open_chat_session(
        self, *, device_id: str, device_serial: str, mode: str = "classic"
    ) -> TaskSessionRecord | None:
        self._ensure_ready()
        with self._lock:
            return self._row_to_session(
                self._fetchone(
                    """
                    SELECT * FROM task_sessions
                    WHERE kind = 'chat'
                      AND mode = ?
                      AND device_id = ?
                      AND device_serial = ?
                      AND status = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (mode, device_id, device_serial, TaskSessionStatus.OPEN.value),
                )
            )

    def archive_session(self, session_id: str) -> TaskSessionRecord | None:
        self._ensure_ready()
        with trace_span(
            "task_store.session.archive",
            attrs={"session_id": session_id},
        ):
            with self._lock:
                assert self._conn is not None
                self._conn.execute(
                    """
                    UPDATE task_sessions
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (TaskSessionStatus.ARCHIVED.value, _now_iso(), session_id),
                )
                self._conn.commit()
                return self.get_session(session_id)

    def _append_event_locked(
        self,
        *,
        task_id: str,
        event_type: str,
        role: str,
        payload: dict[str, Any],
    ) -> TaskEventRecord:
        assert self._conn is not None
        row = self._fetchone(
            "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM task_events WHERE task_id = ?",
            (task_id,),
        )
        next_seq = int(row["max_seq"]) + 1 if row is not None else 1
        created_at = _now_iso()
        self._conn.execute(
            """
            INSERT INTO task_events (task_id, seq, event_type, role, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                next_seq,
                event_type,
                role,
                json.dumps(payload, ensure_ascii=False),
                created_at,
            ),
        )
        return {
            "task_id": task_id,
            "seq": next_seq,
            "event_type": event_type,
            "role": role,
            "payload": payload,
            "created_at": created_at,
        }

    def append_event(
        self,
        *,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        role: str = "assistant",
    ) -> TaskEventRecord:
        self._ensure_ready()
        with trace_span(
            "task_store.event.append",
            attrs={
                "task_id": task_id,
                "event_type": event_type,
                "role": role,
                "payload_keys": sorted(payload.keys()),
            },
        ) as span:
            with self._lock:
                assert self._conn is not None
                event = self._append_event_locked(
                    task_id=task_id,
                    event_type=event_type,
                    role=role,
                    payload=payload,
                )
                span.set_attribute("seq", event.get("seq"))
                self._conn.commit()
                return event

    def create_task_run(
        self,
        *,
        source: str,
        executor_key: str,
        device_id: str,
        device_serial: str,
        input_text: str,
        session_id: str | None = None,
        scheduled_task_id: str | None = None,
        workflow_uuid: str | None = None,
        schedule_fire_id: str | None = None,
        status: str = TaskStatus.QUEUED.value,
        task_id: str | None = None,
        trace_id: str | None = None,
    ) -> TaskRecord:
        self._ensure_ready()
        now = _now_iso()
        record_id = task_id or str(uuid4())
        task_trace_id = trace_id or current_trace_id()
        with trace_span(
            "task_store.task.create",
            attrs={
                "task_id": record_id,
                "source": source,
                "executor_key": executor_key,
                "session_id": session_id,
                "scheduled_task_id": scheduled_task_id,
                "workflow_uuid": workflow_uuid,
                "schedule_fire_id": schedule_fire_id,
                "device_id": device_id,
                "device_serial": device_serial,
                "status": status,
                "trace_id": task_trace_id,
            },
        ):
            with self._lock:
                assert self._conn is not None
                self._conn.execute(
                    """
                    INSERT INTO task_runs (
                        id, source, executor_key, session_id, scheduled_task_id, workflow_uuid,
                        schedule_fire_id, device_id, device_serial, status, input_text,
                        final_message, error_message, stop_reason, trace_id, step_count,
                        created_at, started_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, 0, ?, NULL, NULL)
                    """,
                    (
                        record_id,
                        source,
                        executor_key,
                        session_id,
                        scheduled_task_id,
                        workflow_uuid,
                        schedule_fire_id,
                        device_id,
                        device_serial,
                        status,
                        input_text,
                        task_trace_id,
                        now,
                    ),
                )
                if session_id:
                    self._conn.execute(
                        "UPDATE task_sessions SET updated_at = ? WHERE id = ?",
                        (now, session_id),
                    )
                self._append_event_locked(
                    task_id=record_id,
                    event_type="status",
                    role="system",
                    payload={"status": status},
                )
                self._conn.commit()
                return self.get_task(record_id) or {}

    def set_task_trace_id(self, task_id: str, trace_id: str) -> TaskRecord | None:
        self._ensure_ready()
        with trace_span(
            "task_store.task.set_trace_id",
            attrs={"task_id": task_id, "trace_id": trace_id},
        ):
            with self._lock:
                assert self._conn is not None
                self._conn.execute(
                    "UPDATE task_runs SET trace_id = ? WHERE id = ?",
                    (trace_id, task_id),
                )
                self._conn.commit()
                return self.get_task(task_id)

    def get_task(self, task_id: str) -> TaskRecord | None:
        self._ensure_ready()
        with self._lock:
            return self._row_to_task(
                self._fetchone("SELECT * FROM task_runs WHERE id = ?", (task_id,))
            )

    def list_tasks(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        device_id: str | None = None,
        device_serial: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskRecord], int]:
        self._ensure_ready()
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("status = ?")
            params.append(status)
        if source:
            where.append("source = ?")
            params.append(source)
        if device_id:
            where.append("device_id = ?")
            params.append(device_id)
        if device_serial:
            where.append("device_serial = ?")
            params.append(device_serial)
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._lock:
            rows = self._fetchall(
                f"""
                SELECT * FROM task_runs
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )
            total_row = self._fetchone(
                f"SELECT COUNT(*) AS count FROM task_runs {where_clause}",
                tuple(params),
            )
            total = int(total_row["count"]) if total_row is not None else 0
        return [dict(row) for row in rows], total

    def list_session_tasks(
        self, session_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[TaskRecord], int]:
        return self.list_tasks(session_id=session_id, limit=limit, offset=offset)

    def list_task_events(
        self, task_id: str, *, after_seq: int = 0, limit: int | None = None
    ) -> list[TaskEventRecord]:
        self._ensure_ready()
        limit_clause = ""
        params: list[Any] = [task_id, after_seq]
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(limit)
        with self._lock:
            rows = self._fetchall(
                f"""
                SELECT task_id, seq, event_type, role, payload_json, created_at
                FROM task_events
                WHERE task_id = ? AND seq > ?
                ORDER BY seq ASC
                {limit_clause}
                """,
                tuple(params),
            )
            events: list[TaskEventRecord] = []
            for row in rows:
                event = self._row_to_event(row)
                if event is not None:
                    events.append(event)
            return events

    def get_task_event_count(self, task_id: str) -> int:
        self._ensure_ready()
        with self._lock:
            row = self._fetchone(
                "SELECT COUNT(*) AS count FROM task_events WHERE task_id = ?",
                (task_id,),
            )
            return int(row["count"]) if row is not None else 0

    def claim_next_queued_task(self, device_id: str) -> TaskRecord | None:
        self._ensure_ready()
        with trace_span(
            "task_store.task.claim",
            attrs={"device_id": device_id, "target_status": TaskStatus.QUEUED.value},
        ) as span:
            with self._lock:
                assert self._conn is not None
                row = self._fetchone(
                    """
                    SELECT * FROM task_runs
                    WHERE device_id = ? AND status = ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                    """,
                    (device_id, TaskStatus.QUEUED.value),
                )
                if row is None:
                    span.set_attribute("claimed", False)
                    return None

                now = _now_iso()
                cursor = self._conn.execute(
                    """
                    UPDATE task_runs
                    SET status = ?, started_at = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        TaskStatus.RUNNING.value,
                        now,
                        row["id"],
                        TaskStatus.QUEUED.value,
                    ),
                )
                if cursor.rowcount != 1:
                    self._conn.rollback()
                    span.set_attribute("claimed", False)
                    return None

                self._append_event_locked(
                    task_id=row["id"],
                    event_type="status",
                    role="system",
                    payload={"status": TaskStatus.RUNNING.value},
                )
                self._conn.commit()
                span.set_attributes({"claimed": True, "task_id": str(row["id"])})
                return self.get_task(str(row["id"]))

    def update_task_terminal(
        self,
        *,
        task_id: str,
        status: str,
        final_message: str,
        error_message: str | None,
        stop_reason: str | None = None,
        step_count: int = 0,
        trace_id: str | None = None,
    ) -> TaskRecord | None:
        self._ensure_ready()
        task_trace_id = trace_id or current_trace_id()
        with trace_span(
            "task_store.task.finish",
            attrs={
                "task_id": task_id,
                "status": status,
                "stop_reason": stop_reason,
                "step_count": step_count,
                "trace_id": task_trace_id,
            },
        ):
            with self._lock:
                assert self._conn is not None
                self._conn.execute(
                    """
                    UPDATE task_runs
                    SET status = ?, final_message = ?, error_message = ?, stop_reason = ?,
                        step_count = ?, trace_id = COALESCE(?, trace_id), finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        final_message,
                        error_message,
                        stop_reason,
                        step_count,
                        task_trace_id,
                        _now_iso(),
                        task_id,
                    ),
                )
                self._append_event_locked(
                    task_id=task_id,
                    event_type="status",
                    role="system",
                    payload={"status": status},
                )
                self._conn.commit()
                return self.get_task(task_id)

    def cancel_queued_task(
        self, task_id: str, message: str = "Task cancelled before execution"
    ) -> TaskRecord | None:
        self._ensure_ready()
        with trace_span(
            "task_store.task.cancel",
            attrs={"task_id": task_id},
        ) as span:
            with self._lock:
                assert self._conn is not None
                row = self._fetchone("SELECT * FROM task_runs WHERE id = ?", (task_id,))
                if row is None or row["status"] != TaskStatus.QUEUED.value:
                    span.set_attribute("cancelled", False)
                    return None

                finished_at = _now_iso()
                self._conn.execute(
                    """
                    UPDATE task_runs
                    SET status = ?, final_message = ?, error_message = ?, stop_reason = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        TaskStatus.CANCELLED.value,
                        message,
                        message,
                        "user_stopped",
                        finished_at,
                        task_id,
                    ),
                )
                self._append_event_locked(
                    task_id=task_id,
                    event_type="cancelled",
                    role="assistant",
                    payload={"message": message},
                )
                self._append_event_locked(
                    task_id=task_id,
                    event_type="status",
                    role="system",
                    payload={"status": TaskStatus.CANCELLED.value},
                )
                self._conn.commit()
                span.set_attribute("cancelled", True)
                return self.get_task(task_id)

    def mark_running_tasks_interrupted(
        self,
        message: str = "Task interrupted because the service restarted",
    ) -> int:
        self._ensure_ready()
        with trace_span("task_store.task.interrupt_running") as span:
            with self._lock:
                assert self._conn is not None
                rows = self._fetchall(
                    "SELECT id FROM task_runs WHERE status = ?",
                    (TaskStatus.RUNNING.value,),
                )
                if not rows:
                    span.set_attribute("interrupted_count", 0)
                    return 0

                now = _now_iso()
                for row in rows:
                    task_id = str(row["id"])
                    self._conn.execute(
                        """
                        UPDATE task_runs
                        SET status = ?, final_message = ?, error_message = ?, stop_reason = ?, finished_at = ?
                        WHERE id = ?
                        """,
                        (
                            TaskStatus.INTERRUPTED.value,
                            message,
                            message,
                            "service_interrupted",
                            now,
                            task_id,
                        ),
                    )
                    self._append_event_locked(
                        task_id=task_id,
                        event_type="status",
                        role="system",
                        payload={"status": TaskStatus.INTERRUPTED.value},
                    )
                    self._append_event_locked(
                        task_id=task_id,
                        event_type="error",
                        role="assistant",
                        payload={"message": message},
                    )
                self._conn.commit()
                span.set_attribute("interrupted_count", len(rows))
                return len(rows)

    def get_queued_device_ids(self) -> list[str]:
        self._ensure_ready()
        with self._lock:
            rows = self._fetchall(
                """
                SELECT DISTINCT device_id
                FROM task_runs
                WHERE status = ?
                ORDER BY device_id ASC
                """,
                (TaskStatus.QUEUED.value,),
            )
            return [str(row["device_id"]) for row in rows]

    def get_latest_active_chat_task(
        self, device_id: str, mode: str | None = None
    ) -> TaskRecord | None:
        self._ensure_ready()
        params: list[Any] = [
            device_id,
            TaskStatus.QUEUED.value,
            TaskStatus.RUNNING.value,
        ]
        join_clause = ""
        mode_clause = ""
        if mode is not None:
            join_clause = (
                "JOIN task_sessions ON task_sessions.id = task_runs.session_id"
            )
            mode_clause = "AND task_sessions.mode = ?"
            params.append(mode)
        with self._lock:
            return self._row_to_task(
                self._fetchone(
                    f"""
                    SELECT task_runs.*
                    FROM task_runs
                    {join_clause}
                    WHERE source = 'chat'
                      AND device_id = ?
                      AND status IN (?, ?)
                      {mode_clause}
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    tuple(params),
                )
            )

    def get_latest_active_session_task(self, session_id: str) -> TaskRecord | None:
        self._ensure_ready()
        with self._lock:
            return self._row_to_task(
                self._fetchone(
                    """
                    SELECT *
                    FROM task_runs
                    WHERE session_id = ?
                      AND status IN (?, ?)
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (
                        session_id,
                        TaskStatus.QUEUED.value,
                        TaskStatus.RUNNING.value,
                    ),
                )
            )

    def delete_task(self, task_id: str) -> bool:
        self._ensure_ready()
        with self._lock:
            assert self._conn is not None
            cursor = self._conn.execute(
                "DELETE FROM task_runs WHERE id = ?", (task_id,)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def clear_device_history(self, device_serial: str) -> int:
        self._ensure_ready()
        with self._lock:
            assert self._conn is not None
            cursor = self._conn.execute(
                """
                DELETE FROM task_runs
                WHERE device_serial = ?
                  AND status IN (?, ?, ?, ?)
                """,
                (
                    device_serial,
                    TaskStatus.SUCCEEDED.value,
                    TaskStatus.FAILED.value,
                    TaskStatus.CANCELLED.value,
                    TaskStatus.INTERRUPTED.value,
                ),
            )
            self._conn.commit()
            return cursor.rowcount

    def get_latest_schedule_summary(
        self, scheduled_task_id: str
    ) -> dict[str, Any] | None:
        self._ensure_ready()
        with self._lock:
            fire_row = self._fetchone(
                """
                SELECT schedule_fire_id
                FROM task_runs
                WHERE scheduled_task_id = ?
                  AND schedule_fire_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (scheduled_task_id,),
            )
            if fire_row is None:
                return None

            schedule_fire_id = str(fire_row["schedule_fire_id"])
            rows = self._fetchall(
                """
                SELECT *
                FROM task_runs
                WHERE scheduled_task_id = ? AND schedule_fire_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (scheduled_task_id, schedule_fire_id),
            )
            tasks = [dict(row) for row in rows]
        if not tasks:
            return None
        if any(task["status"] not in TERMINAL_TASK_STATUSES for task in tasks):
            return None

        total_count = len(tasks)
        success_count = sum(
            1 for task in tasks if task["status"] == TaskStatus.SUCCEEDED.value
        )
        if success_count == total_count:
            status = "success"
            success = True
        elif success_count > 0:
            status = "partial"
            success = False
        else:
            status = "failure"
            success = False

        message_parts = []
        for task in tasks:
            icon = "✓" if task["status"] == TaskStatus.SUCCEEDED.value else "✗"
            short_device = task["device_serial"]
            result = task["final_message"] or task["error_message"] or task["status"]
            message_parts.append(f"{icon} {short_device}: {result[:30]}")

        last_run_time = max(
            task["finished_at"] or task["started_at"] or task["created_at"]
            for task in tasks
        )
        return {
            "schedule_fire_id": schedule_fire_id,
            "last_run_time": last_run_time,
            "last_run_success": success,
            "last_run_status": status,
            "last_run_success_count": success_count,
            "last_run_total_count": total_count,
            "last_run_message": " | ".join(message_parts)[:500],
        }


task_store = TaskStore()
