"""Task API routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from AutoGLM_GUI.schemas import (
    TaskCancelResponse,
    TaskEventListResponse,
    TaskEventResponse,
    TaskRunListResponse,
    TaskRunResponse,
    TaskSessionCreate,
    TaskSessionResetResponse,
    TaskSessionResponse,
    TaskSubmitRequest,
)
from AutoGLM_GUI.layered_agent_service import reset_session as reset_layered_session
from AutoGLM_GUI.task_manager import task_manager
from AutoGLM_GUI.task_store import (
    TERMINAL_TASK_STATUSES,
    TaskEventRecord,
    TaskRecord,
    TaskSessionRecord,
    TaskSessionStatus,
    TaskStatus,
    task_store,
)

router = APIRouter()


def _task_run_response(record: TaskRecord) -> TaskRunResponse:
    started_at = record.get("started_at")
    finished_at = record.get("finished_at")
    duration_ms: int | None = None
    if started_at and finished_at:
        try:
            from datetime import datetime

            start = datetime.fromisoformat(str(started_at))
            end = datetime.fromisoformat(str(finished_at))
            duration_ms = int((end - start).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass

    return TaskRunResponse(
        id=str(record["id"]),
        source=str(record["source"]),
        executor_key=str(record["executor_key"]),
        session_id=str(record["session_id"])
        if record.get("session_id") is not None
        else None,
        scheduled_task_id=str(record["scheduled_task_id"])
        if record.get("scheduled_task_id") is not None
        else None,
        workflow_uuid=str(record["workflow_uuid"])
        if record.get("workflow_uuid") is not None
        else None,
        schedule_fire_id=str(record["schedule_fire_id"])
        if record.get("schedule_fire_id") is not None
        else None,
        device_id=str(record["device_id"]),
        device_serial=str(record["device_serial"]),
        status=TaskStatus(str(record["status"])),
        input_text=str(record["input_text"]),
        final_message=str(record["final_message"])
        if record.get("final_message") is not None
        else None,
        error_message=str(record["error_message"])
        if record.get("error_message") is not None
        else None,
        stop_reason=str(record.get("stop_reason"))
        if record.get("stop_reason") is not None
        else None,
        trace_id=str(record.get("trace_id"))
        if record.get("trace_id") is not None
        else None,
        step_count=int(record["step_count"]),
        created_at=str(record["created_at"]),
        started_at=str(record["started_at"])
        if record.get("started_at") is not None
        else None,
        finished_at=str(record["finished_at"])
        if record.get("finished_at") is not None
        else None,
        duration_ms=duration_ms,
    )


def _task_session_response(record: TaskSessionRecord) -> TaskSessionResponse:
    return TaskSessionResponse(
        id=str(record["id"]),
        kind=str(record["kind"]),
        mode=str(record["mode"]),
        device_id=str(record["device_id"]),
        device_serial=str(record["device_serial"]),
        status=TaskSessionStatus(str(record["status"])),
        created_at=str(record["created_at"]),
        updated_at=str(record["updated_at"]),
    )


def _task_event_response(record: TaskEventRecord) -> TaskEventResponse:
    return TaskEventResponse(
        task_id=str(record["task_id"]),
        seq=int(record["seq"]),
        event_type=str(record["event_type"]),
        role=str(record["role"]),
        payload=dict(record["payload"]),
        created_at=str(record["created_at"]),
    )


@router.post("/api/task-sessions", response_model=TaskSessionResponse)
async def create_task_session(request: TaskSessionCreate) -> TaskSessionResponse:
    session = await task_manager.create_chat_session(
        device_id=request.device_id,
        device_serial=request.device_serial,
        mode=request.mode,
    )
    return _task_session_response(session)


@router.get("/api/task-sessions/{session_id}", response_model=TaskSessionResponse)
async def get_task_session(session_id: str) -> TaskSessionResponse:
    session = await task_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Task session not found")
    return _task_session_response(session)


@router.post(
    "/api/task-sessions/{session_id}/reset",
    response_model=TaskSessionResetResponse,
)
async def reset_task_session(session_id: str) -> TaskSessionResetResponse:
    session = await task_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Task session not found")

    active_task = await asyncio.to_thread(
        task_store.get_latest_active_session_task,
        session_id,
    )
    if active_task is not None:
        await task_manager.cancel_task(str(active_task["id"]))
        await task_manager.wait_for_task(str(active_task["id"]))

    if str(session["mode"]) == "layered":
        reset_layered_session(session_id)

    archived_session = await task_manager.archive_session(session_id)
    return TaskSessionResetResponse(
        success=True,
        message=f"Session {session_id} cleared",
        session=(
            _task_session_response(archived_session)
            if archived_session is not None
            else None
        ),
    )


@router.get(
    "/api/task-sessions/{session_id}/tasks",
    response_model=TaskRunListResponse,
)
async def list_task_session_tasks(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TaskRunListResponse:
    session = await task_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Task session not found")

    tasks, total = await asyncio.to_thread(
        task_store.list_session_tasks,
        session_id,
        limit,
        offset,
    )
    return TaskRunListResponse(
        tasks=[_task_run_response(task) for task in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/task-sessions/{session_id}/tasks",
    response_model=TaskRunResponse,
)
async def submit_task_session_task(
    session_id: str, request: TaskSubmitRequest
) -> TaskRunResponse:
    session = await task_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Task session not found")

    task = await task_manager.submit_chat_task(
        session_id=session_id,
        device_id=str(session["device_id"]),
        device_serial=str(session["device_serial"]),
        message=request.message,
        attachments=[attachment.model_dump() for attachment in request.attachments],
    )
    return _task_run_response(task)


@router.get("/api/tasks", response_model=TaskRunListResponse)
async def list_tasks(
    status: str | None = None,
    source: str | None = None,
    device_id: str | None = None,
    device_serial: str | None = None,
    session_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TaskRunListResponse:
    if status is not None:
        valid = {s.value for s in TaskStatus}
        if status not in valid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid))}",
            )
    tasks, total = await asyncio.to_thread(
        task_store.list_tasks,
        status=status,
        source=source,
        device_id=device_id,
        device_serial=device_serial,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return TaskRunListResponse(
        tasks=[_task_run_response(task) for task in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/tasks/{task_id}", response_model=TaskRunResponse)
async def get_task(task_id: str) -> TaskRunResponse:
    task = await asyncio.to_thread(task_store.get_task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_run_response(task)


@router.get("/api/tasks/{task_id}/events", response_model=TaskEventListResponse)
async def get_task_events(
    task_id: str,
    after_seq: int = Query(default=0, ge=0),
) -> TaskEventListResponse:
    task = await asyncio.to_thread(task_store.get_task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    events = await asyncio.to_thread(
        task_store.list_task_events,
        task_id,
        after_seq=after_seq,
    )
    return TaskEventListResponse(
        events=[_task_event_response(event) for event in events]
    )


@router.get("/api/tasks/{task_id}/stream")
async def stream_task_events(
    task_id: str,
    after_seq: int = Query(default=0, ge=0),
) -> StreamingResponse:
    task = await asyncio.to_thread(task_store.get_task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        last_seq = after_seq
        while True:
            events = await asyncio.to_thread(
                task_store.list_task_events,
                task_id,
                after_seq=last_seq,
            )
            for event in events:
                last_seq = max(last_seq, int(event["seq"]))
                response = _task_event_response(event)
                payload = response.model_dump()
                yield f"event: {response.event_type}\n"
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            current_task = await asyncio.to_thread(task_store.get_task, task_id)
            if (
                current_task is None or current_task["status"] in TERMINAL_TASK_STATUSES
            ) and not events:
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(task_id: str) -> TaskCancelResponse:
    task = await task_manager.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    success = (
        task["status"] not in TERMINAL_TASK_STATUSES or task["status"] == "CANCELLED"
    )
    message = (
        "Task cancellation requested"
        if task["status"] not in TERMINAL_TASK_STATUSES
        else "Task already finished"
    )
    if task["status"] == "CANCELLED":
        success = True
        message = "Task cancelled"
    return TaskCancelResponse(
        success=success,
        message=message,
        task=_task_run_response(task),
    )
