"""History API routes."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from AutoGLM_GUI.history_manager import history_manager
from AutoGLM_GUI.scheduler_manager import scheduler_manager
from AutoGLM_GUI.models.history import ConversationRecord
from AutoGLM_GUI.schemas import (
    HistoryListResponse,
    HistoryRecordResponse,
    MessageRecordResponse,
    StepTimingSummaryResponse,
    TraceSummaryResponse,
)
from AutoGLM_GUI.task_store import TERMINAL_TASK_STATUSES, TaskStatus, task_store

router = APIRouter()

# Maps the chat execution mode to the task-run executor keys and the legacy
# ``ConversationRecord.source`` values that belong to it.  Used to keep the
# per-mode history popovers (classic vs. layered) from showing each other's runs.
_MODE_EXECUTOR_KEYS: dict[str, set[str]] = {
    "classic": {"classic_chat"},
    "layered": {"layered_chat"},
}
_MODE_LEGACY_SOURCES: dict[str, set[str]] = {
    "classic": {"chat"},
    "layered": {"layered"},
}
_TRACE_SUMMARY_FIELDS = set(TraceSummaryResponse.model_fields)


def _build_history_record_response(record: ConversationRecord) -> HistoryRecordResponse:
    return HistoryRecordResponse(
        id=record.id,
        task_text=record.task_text,
        final_message=record.final_message,
        success=record.success,
        steps=record.steps,
        start_time=record.start_time.isoformat(),
        end_time=record.end_time.isoformat() if record.end_time else None,
        duration_ms=record.duration_ms,
        source=record.source,
        source_detail=record.source_detail,
        error_message=record.error_message,
        trace_id=record.trace_id,
        step_timings=[
            StepTimingSummaryResponse(**timing.to_dict())
            for timing in record.step_timings
        ],
        trace_summary=TraceSummaryResponse(**record.trace_summary.to_dict())
        if record.trace_summary
        else None,
        messages=[
            MessageRecordResponse(
                role=message.role,
                content=message.content,
                timestamp=message.timestamp.isoformat(),
                thinking=message.thinking,
                action=message.action,
                step=message.step,
            )
            for message in record.messages
        ],
    )


def _tool_result_text(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, str):
        return result
    if result is None:
        return ""
    return json.dumps(result, ensure_ascii=False)


def _trace_summary_from_payload(
    payload: dict[str, Any],
) -> TraceSummaryResponse | None:
    raw_summary = payload.get("summary", payload)
    if not isinstance(raw_summary, dict):
        return None
    summary = {
        key: raw_summary[key] for key in _TRACE_SUMMARY_FIELDS if key in raw_summary
    }
    missing = _TRACE_SUMMARY_FIELDS - set(summary)
    if missing:
        return None
    return TraceSummaryResponse(**summary)


def _step_timings_from_trace_payload(
    payload: dict[str, Any],
) -> list[StepTimingSummaryResponse]:
    raw_step_summaries = payload.get("step_summaries")
    if not isinstance(raw_step_summaries, list):
        return []

    step_timings: list[StepTimingSummaryResponse] = []
    for raw_step_summary in raw_step_summaries:
        if isinstance(raw_step_summary, dict):
            step_timings.append(StepTimingSummaryResponse(**raw_step_summary))
    return step_timings


def _trace_summary_from_step_timings(
    trace_id: str | None,
    step_timings: list[StepTimingSummaryResponse],
) -> TraceSummaryResponse | None:
    if not step_timings:
        return None
    resolved_trace_id = trace_id or step_timings[0].trace_id
    return TraceSummaryResponse(
        trace_id=resolved_trace_id,
        steps=len(step_timings),
        total_duration_ms=round(sum(t.total_duration_ms for t in step_timings), 3),
        screenshot_duration_ms=round(
            sum(t.screenshot_duration_ms for t in step_timings), 3
        ),
        current_app_duration_ms=round(
            sum(t.current_app_duration_ms for t in step_timings), 3
        ),
        llm_duration_ms=round(sum(t.llm_duration_ms for t in step_timings), 3),
        parse_action_duration_ms=round(
            sum(t.parse_action_duration_ms for t in step_timings), 3
        ),
        execute_action_duration_ms=round(
            sum(t.execute_action_duration_ms for t in step_timings), 3
        ),
        update_context_duration_ms=round(
            sum(t.update_context_duration_ms for t in step_timings), 3
        ),
        adb_duration_ms=round(sum(t.adb_duration_ms for t in step_timings), 3),
        sleep_duration_ms=round(sum(t.sleep_duration_ms for t in step_timings), 3),
        other_duration_ms=round(sum(t.other_duration_ms for t in step_timings), 3),
    )


def _build_history_record_from_task(record: dict[str, Any]) -> HistoryRecordResponse:
    events = task_store.list_task_events(record["id"])
    step_timings: list[StepTimingSummaryResponse] = []
    trace_summary: TraceSummaryResponse | None = None
    messages: list[MessageRecordResponse] = [
        MessageRecordResponse(
            role="user",
            content=record["input_text"],
            timestamp=record["created_at"],
        )
    ]
    # Sequence index for layered tool-call cycles so the UI can group a tool
    # call together with its result under a single "step".
    layered_step = 0
    for event in events:
        event_type = event["event_type"]
        payload = event["payload"]
        if event_type == "step":
            messages.append(
                MessageRecordResponse(
                    role="assistant",
                    content="",
                    timestamp=event["created_at"],
                    thinking=payload.get("thinking"),
                    action=payload.get("action"),
                    step=payload.get("step"),
                )
            )
            timings = payload.get("timings")
            if isinstance(timings, dict):
                step_timings.append(StepTimingSummaryResponse(**timings))
        elif event_type == "trace_summary":
            trace_summary = _trace_summary_from_payload(payload)
            existing_timing_keys = {
                (timing.trace_id, timing.step) for timing in step_timings
            }
            for timing in _step_timings_from_trace_payload(payload):
                timing_key = (timing.trace_id, timing.step)
                if timing_key not in existing_timing_keys:
                    step_timings.append(timing)
                    existing_timing_keys.add(timing_key)
        elif event_type == "tool_call":
            layered_step += 1
            messages.append(
                MessageRecordResponse(
                    role="assistant",
                    content="",
                    timestamp=event["created_at"],
                    action={
                        "tool_name": payload.get("tool_name"),
                        "tool_args": payload.get("tool_args", {}),
                    },
                    step=layered_step,
                )
            )
        elif event_type == "tool_result":
            messages.append(
                MessageRecordResponse(
                    role="assistant",
                    content=_tool_result_text(payload),
                    timestamp=event["created_at"],
                    step=layered_step or None,
                )
            )
        elif event_type == "message":
            content = payload.get("content")
            if content:
                messages.append(
                    MessageRecordResponse(
                        role="assistant",
                        content=str(content),
                        timestamp=event["created_at"],
                    )
                )

    source_detail = record.get("session_id") or ""
    if record["source"] == "scheduled" and record.get("scheduled_task_id"):
        task = scheduler_manager.get_task(str(record["scheduled_task_id"]))
        if task is not None:
            source_detail = task.name

    final_message = (
        record.get("final_message")
        or record.get("error_message")
        or record.get("status")
        or ""
    )
    success = record["status"] == TaskStatus.SUCCEEDED.value
    end_time = record.get("finished_at")
    start_time = record.get("started_at") or record["created_at"]
    trace_id = str(record["trace_id"]) if record.get("trace_id") is not None else None
    if trace_summary is None:
        trace_summary = _trace_summary_from_step_timings(trace_id, step_timings)
    if trace_id is None and trace_summary is not None:
        trace_id = trace_summary.trace_id

    duration_ms = 0
    if end_time:
        try:
            from datetime import datetime

            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
        except ValueError:
            duration_ms = 0

    return HistoryRecordResponse(
        id=str(record["id"]),
        task_text=str(record["input_text"]),
        final_message=str(final_message),
        success=success,
        steps=int(record.get("step_count", 0)),
        start_time=str(start_time),
        end_time=str(end_time) if end_time else None,
        duration_ms=duration_ms,
        source=str(record["source"]),
        source_detail=str(source_detail),
        error_message=str(record["error_message"])
        if record.get("error_message") is not None
        else None,
        trace_id=trace_id,
        step_timings=step_timings,
        trace_summary=trace_summary,
        messages=messages,
    )


def _is_terminal_task_record(record: dict[str, Any]) -> bool:
    return record["status"] in TERMINAL_TASK_STATUSES


def _list_merged_history(
    serialno: str, mode: str | None = None
) -> list[HistoryRecordResponse]:
    task_records, _ = task_store.list_tasks(
        device_serial=serialno, limit=10000, offset=0
    )
    history_total = history_manager.get_total_count(serialno)
    legacy_records = history_manager.list_records(serialno, history_total, 0)

    if mode is not None:
        allowed_executor_keys = _MODE_EXECUTOR_KEYS.get(mode, set())
        allowed_legacy_sources = _MODE_LEGACY_SOURCES.get(mode, set())
        task_records = [
            record
            for record in task_records
            if record.get("executor_key") in allowed_executor_keys
        ]
        legacy_records = [
            record
            for record in legacy_records
            if record.source in allowed_legacy_sources
        ]

    merged = [
        _build_history_record_from_task(record)
        for record in task_records
        if _is_terminal_task_record(record)
    ]
    merged.extend(_build_history_record_response(record) for record in legacy_records)
    merged.sort(key=lambda item: item.start_time, reverse=True)
    return merged


@router.get("/api/history/{serialno}", response_model=HistoryListResponse)
def list_history(
    serialno: str, limit: int = 50, offset: int = 0, mode: str | None = None
) -> HistoryListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")
    if mode is not None and mode not in _MODE_EXECUTOR_KEYS:
        raise HTTPException(
            status_code=400, detail="mode must be 'classic' or 'layered'"
        )

    merged_records = _list_merged_history(serialno, mode)
    total = len(merged_records)
    records = merged_records[offset : offset + limit]

    return HistoryListResponse(
        records=records,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/history/{serialno}/{record_id}", response_model=HistoryRecordResponse)
def get_history_record(serialno: str, record_id: str) -> HistoryRecordResponse:
    task_record = task_store.get_task(record_id)
    if (
        task_record is not None
        and task_record["device_serial"] == serialno
        and _is_terminal_task_record(task_record)
    ):
        return _build_history_record_from_task(task_record)

    record = history_manager.get_record(serialno, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    return _build_history_record_response(record)


@router.delete("/api/history/{serialno}/{record_id}")
def delete_history_record(serialno: str, record_id: str) -> dict[str, Any]:
    task_record = task_store.get_task(record_id)
    if task_record is not None and task_record["device_serial"] == serialno:
        if not _is_terminal_task_record(task_record):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete task history while task is still active",
            )
        success = task_store.delete_task(record_id)
    else:
        success = history_manager.delete_record(serialno, record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "message": "Record deleted"}


@router.delete("/api/history/{serialno}")
def clear_history(serialno: str) -> dict[str, Any]:
    task_store.clear_device_history(serialno)
    history_manager.clear_device_history(serialno)
    return {"success": True, "message": f"History cleared for {serialno}"}
