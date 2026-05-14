"""History API routes."""

import json
from collections.abc import Callable
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request

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
from AutoGLM_GUI.trace import delete_replay_run

router = APIRouter()

# Maps the chat execution mode to the task-run executor keys and the legacy
# ``ConversationRecord.source`` values that belong to it.  Used to keep the
# per-mode history popovers (classic vs. layered) from showing each other's runs.
_MODE_EXECUTOR_KEYS: dict[str, set[str]] = {
    "classic": {"classic_chat"},
    "layered": {"layered_chat"},
    "chat": {"chat"},
}
_MODE_LEGACY_SOURCES: dict[str, set[str]] = {
    "classic": {"chat"},
    "layered": {"layered"},
    "chat": {"chat"},
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


def _build_history_record_from_task(
    record: dict[str, Any], *, include_attachments: bool = True
) -> HistoryRecordResponse:
    events = task_store.list_task_events(record["id"])
    user_message_event = next(
        (event for event in events if event["event_type"] == "user_message"),
        None,
    )
    user_message_payload = (
        dict(user_message_event["payload"]) if user_message_event is not None else {}
    )
    user_attachments = user_message_payload.get("attachments", [])
    if not isinstance(user_attachments, list):
        user_attachments = []
    if not include_attachments:
        user_attachments = []
    step_timings: list[StepTimingSummaryResponse] = []
    trace_summary: TraceSummaryResponse | None = None
    messages: list[MessageRecordResponse] = [
        MessageRecordResponse(
            role="user",
            content=str(user_message_payload.get("message", record["input_text"])),
            timestamp=record["created_at"],
            attachments=user_attachments,
        )
    ]
    # Track the latest assistant message so thinking/content events can
    # update it instead of creating duplicates.
    latest_assistant_msg: MessageRecordResponse | None = None
    # Sequence index for layered tool-call cycles so the UI can group a tool
    # call together with its result under a single "step".
    layered_step = 0
    for event in events:
        event_type = event["event_type"]
        payload = event["payload"]
        if event_type == "user_message":
            continue
        if event_type == "step":
            latest_assistant_msg = MessageRecordResponse(
                role="assistant",
                content="",
                timestamp=event["created_at"],
                thinking=payload.get("thinking"),
                action=payload.get("action"),
                step=payload.get("step"),
            )
            messages.append(latest_assistant_msg)
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
            latest_assistant_msg = MessageRecordResponse(
                role="assistant",
                content="",
                timestamp=event["created_at"],
                action={
                    "tool_name": payload.get("tool_name"),
                    "tool_args": payload.get("tool_args", {}),
                },
                step=layered_step,
            )
            messages.append(latest_assistant_msg)
        elif event_type == "tool_result":
            latest_assistant_msg = MessageRecordResponse(
                role="assistant",
                content=_tool_result_text(payload),
                timestamp=event["created_at"],
                step=layered_step or None,
            )
            messages.append(latest_assistant_msg)
        elif event_type == "message":
            content = payload.get("content")
            if content:
                latest_assistant_msg = MessageRecordResponse(
                    role="assistant",
                    content=str(content),
                    timestamp=event["created_at"],
                )
                messages.append(latest_assistant_msg)
        # Chat mode events: thinking, content, done
        elif event_type == "thinking":
            chunk = payload.get("chunk", "")
            if chunk:
                if (
                    latest_assistant_msg is not None
                    and latest_assistant_msg.role == "assistant"
                    and latest_assistant_msg.step is None
                    and latest_assistant_msg.action is None
                ):
                    # Update existing assistant message thinking
                    latest_assistant_msg.thinking = chunk
                else:
                    latest_assistant_msg = MessageRecordResponse(
                        role="assistant",
                        content="",
                        timestamp=event["created_at"],
                        thinking=chunk,
                    )
                    messages.append(latest_assistant_msg)
        elif event_type == "content":
            chunk = payload.get("chunk", "")
            if chunk:
                if (
                    latest_assistant_msg is not None
                    and latest_assistant_msg.role == "assistant"
                    and latest_assistant_msg.step is None
                    and latest_assistant_msg.action is None
                    and latest_assistant_msg.thinking is not None
                ):
                    # If the latest assistant msg already has thinking,
                    # update its content (thinking + content pair).
                    latest_assistant_msg.content = chunk
                elif (
                    latest_assistant_msg is not None
                    and latest_assistant_msg.role == "assistant"
                    and latest_assistant_msg.step is None
                    and latest_assistant_msg.action is None
                    and latest_assistant_msg.content
                ):
                    # Update existing content-only assistant message
                    latest_assistant_msg.content = chunk
                else:
                    latest_assistant_msg = MessageRecordResponse(
                        role="assistant",
                        content=chunk,
                        timestamp=event["created_at"],
                    )
                    messages.append(latest_assistant_msg)
        elif event_type == "done":
            done_message = payload.get("message", "")
            if done_message:
                if (
                    latest_assistant_msg is not None
                    and latest_assistant_msg.role == "assistant"
                    and latest_assistant_msg.step is None
                    and latest_assistant_msg.action is None
                    and not latest_assistant_msg.content
                ):
                    # Only update if the latest assistant msg has no content yet
                    # (e.g. a thinking-only msg or an empty msg).
                    latest_assistant_msg.content = done_message
                elif (
                    latest_assistant_msg is not None
                    and latest_assistant_msg.role == "assistant"
                    and latest_assistant_msg.step is None
                    and latest_assistant_msg.action is None
                    and latest_assistant_msg.content == done_message
                ):
                    # Content already matches done_message (chat mode content
                    # followed by done with the same text) – skip duplicate.
                    pass
                else:
                    latest_assistant_msg = MessageRecordResponse(
                        role="assistant",
                        content=done_message,
                        timestamp=event["created_at"],
                    )
                    messages.append(latest_assistant_msg)

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


def _merge_chat_history_by_session(
    records: list[HistoryRecordResponse],
) -> list[HistoryRecordResponse]:
    """将同一 session 的多个 chat task_run 合并为一个历史记录项."""
    from collections import OrderedDict

    session_groups: OrderedDict[str, list[HistoryRecordResponse]] = OrderedDict()
    for record in records:
        session_id = record.source_detail
        if not session_id:
            # 没有 session_id 的单独保留
            session_groups[record.id] = [record]
        else:
            if session_id not in session_groups:
                session_groups[session_id] = []
            session_groups[session_id].append(record)

    merged_records: list[HistoryRecordResponse] = []
    for group in session_groups.values():
        if len(group) == 1:
            merged_records.append(group[0])
            continue

        # 按 start_time 排序，确保消息顺序正确
        group.sort(key=lambda r: r.start_time)

        # 合并 messages
        all_messages: list[MessageRecordResponse] = []
        for record in group:
            all_messages.extend(record.messages)
        # 按 timestamp 排序
        all_messages.sort(key=lambda m: m.timestamp)

        # 合并 step_timings
        all_step_timings: list[StepTimingSummaryResponse] = []
        for record in group:
            all_step_timings.extend(record.step_timings)

        # 合并 trace_summary
        merged_trace_summary: TraceSummaryResponse | None = None
        for record in group:
            if record.trace_summary is not None:
                if merged_trace_summary is None:
                    merged_trace_summary = TraceSummaryResponse(
                        trace_id=record.trace_summary.trace_id,
                        steps=record.trace_summary.steps,
                        total_duration_ms=record.trace_summary.total_duration_ms,
                        screenshot_duration_ms=record.trace_summary.screenshot_duration_ms,
                        current_app_duration_ms=record.trace_summary.current_app_duration_ms,
                        llm_duration_ms=record.trace_summary.llm_duration_ms,
                        parse_action_duration_ms=record.trace_summary.parse_action_duration_ms,
                        execute_action_duration_ms=record.trace_summary.execute_action_duration_ms,
                        update_context_duration_ms=record.trace_summary.update_context_duration_ms,
                        adb_duration_ms=record.trace_summary.adb_duration_ms,
                        sleep_duration_ms=record.trace_summary.sleep_duration_ms,
                        other_duration_ms=record.trace_summary.other_duration_ms,
                    )
                else:
                    merged_trace_summary = TraceSummaryResponse(
                        trace_id=merged_trace_summary.trace_id,
                        steps=merged_trace_summary.steps + record.trace_summary.steps,
                        total_duration_ms=round(
                            merged_trace_summary.total_duration_ms
                            + record.trace_summary.total_duration_ms,
                            3,
                        ),
                        screenshot_duration_ms=round(
                            merged_trace_summary.screenshot_duration_ms
                            + record.trace_summary.screenshot_duration_ms,
                            3,
                        ),
                        current_app_duration_ms=round(
                            merged_trace_summary.current_app_duration_ms
                            + record.trace_summary.current_app_duration_ms,
                            3,
                        ),
                        llm_duration_ms=round(
                            merged_trace_summary.llm_duration_ms
                            + record.trace_summary.llm_duration_ms,
                            3,
                        ),
                        parse_action_duration_ms=round(
                            merged_trace_summary.parse_action_duration_ms
                            + record.trace_summary.parse_action_duration_ms,
                            3,
                        ),
                        execute_action_duration_ms=round(
                            merged_trace_summary.execute_action_duration_ms
                            + record.trace_summary.execute_action_duration_ms,
                            3,
                        ),
                        update_context_duration_ms=round(
                            merged_trace_summary.update_context_duration_ms
                            + record.trace_summary.update_context_duration_ms,
                            3,
                        ),
                        adb_duration_ms=round(
                            merged_trace_summary.adb_duration_ms
                            + record.trace_summary.adb_duration_ms,
                            3,
                        ),
                        sleep_duration_ms=round(
                            merged_trace_summary.sleep_duration_ms
                            + record.trace_summary.sleep_duration_ms,
                            3,
                        ),
                        other_duration_ms=round(
                            merged_trace_summary.other_duration_ms
                            + record.trace_summary.other_duration_ms,
                            3,
                        ),
                    )

        # 计算合并后的字段
        # 对话模式下 steps 表示轮数（task_run 数量），而不是内部 step_count 总和
        total_steps = len(group)
        total_duration_ms = sum(r.duration_ms for r in group)
        all_success = all(r.success for r in group)
        first_task_text = group[0].task_text
        first_start_time = group[0].start_time
        last_end_time = group[-1].end_time
        last_final_message = group[-1].final_message
        first_trace_id = group[0].trace_id
        first_source = group[0].source
        session_id = group[0].source_detail

        merged_records.append(
            HistoryRecordResponse(
                id=session_id,
                task_text=first_task_text,
                final_message=last_final_message,
                success=all_success,
                steps=total_steps,
                start_time=first_start_time,
                end_time=last_end_time,
                duration_ms=total_duration_ms,
                source=first_source,
                source_detail=session_id,
                error_message=None,
                trace_id=first_trace_id,
                step_timings=all_step_timings,
                trace_summary=merged_trace_summary,
                messages=all_messages,
            )
        )

    # 按 start_time 倒序排列
    merged_records.sort(key=lambda item: item.start_time, reverse=True)
    return merged_records


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
        _build_history_record_from_task(record, include_attachments=False)
        for record in task_records
        if _is_terminal_task_record(record)
    ]
    merged.extend(_build_history_record_response(record) for record in legacy_records)

    # 对话模式下按 session 合并同一聊天框的多轮对话
    if mode == "chat":
        merged = _merge_chat_history_by_session(merged)

    merged.sort(key=lambda item: item.start_time, reverse=True)
    return merged


def _has_history_for_serial(serialno: str) -> bool:
    task_records, task_total = task_store.list_tasks(
        device_serial=serialno, limit=1, offset=0
    )
    if task_total > 0 or task_records:
        return True
    return history_manager.get_total_count(serialno) > 0


def _record_path_candidate(history_path: str) -> tuple[str, str] | None:
    if "/" not in history_path:
        return None
    serialno, record_id = history_path.rsplit("/", 1)
    if not serialno or not record_id:
        return None
    return serialno, record_id


def _path_should_resolve_as_record(
    history_path: str, *, force_list: bool = False
) -> bool:
    if force_list:
        return False
    candidate = _record_path_candidate(history_path)
    if candidate is None:
        return False

    serialno, record_id = candidate
    task_record = task_store.get_task(record_id)
    if task_record is not None:
        return task_record["device_serial"] == serialno
    if history_manager.get_record(serialno, record_id) is not None:
        return True
    if _has_history_for_serial(history_path):
        return False
    return _has_history_for_serial(serialno)


def _get_history_record_response(
    serialno: str, record_id: str
) -> HistoryRecordResponse:
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


def _delete_history_record(serialno: str, record_id: str) -> dict[str, Any]:
    task_record = task_store.get_task(record_id)
    trace_id = None
    if task_record is not None and task_record["device_serial"] == serialno:
        if not _is_terminal_task_record(task_record):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete task history while task is still active",
            )
        trace_id = task_record.get("trace_id")
        success = task_store.delete_task(record_id)
    else:
        success = history_manager.delete_record(serialno, record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    if trace_id:
        delete_replay_run(str(trace_id))
    return {"success": True, "message": "Record deleted"}


def _list_history_response(
    serialno: str, limit: int, offset: int, mode: str | None
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


def _clear_history(serialno: str) -> dict[str, Any]:
    trace_ids: list[str] = []
    list_trace_ids = getattr(task_store, "list_terminal_trace_ids_for_device", None)
    if callable(list_trace_ids):
        trace_ids = cast(Callable[[str], list[str]], list_trace_ids)(serialno)
    task_store.clear_device_history(serialno)
    history_manager.clear_device_history(serialno)
    for trace_id in trace_ids:
        delete_replay_run(str(trace_id))
    return {"success": True, "message": f"History cleared for {serialno}"}


@router.get(
    "/api/history/{serialno}/{record_id}",
    response_model=HistoryRecordResponse,
)
def get_history_record(serialno: str, record_id: str) -> HistoryRecordResponse:
    task_record = task_store.get_task(record_id)
    if (
        task_record is not None
        and task_record["device_serial"] == serialno
        and _is_terminal_task_record(task_record)
    ):
        return _build_history_record_from_task(task_record)

    # 对话模式下 record_id 可能是 session_id，尝试按 session 查找并合并
    session_tasks, _ = task_store.list_tasks(
        device_serial=serialno, session_id=record_id, limit=10000, offset=0
    )
    if session_tasks:
        records = [
            _build_history_record_from_task(r, include_attachments=True)
            for r in session_tasks
            if _is_terminal_task_record(r)
        ]
        if records:
            merged = _merge_chat_history_by_session(records)
            for item in merged:
                if item.id == record_id:
                    return item
            # fallback: 返回合并后的第一个
            return merged[0]

    return _get_history_record_response(serialno, record_id)


@router.delete("/api/history/{serialno}/{record_id}")
def delete_history_record(serialno: str, record_id: str) -> dict[str, Any]:
    task_record = task_store.get_task(record_id)
    if task_record is not None and task_record["device_serial"] == serialno:
        return _delete_history_record(serialno, record_id)

    # 尝试按 session_id 删除（对话模式）
    deleted_count = task_store.delete_tasks_by_session(record_id)
    if deleted_count > 0:
        return {"success": True, "message": "Record deleted"}

    return _delete_history_record(serialno, record_id)


@router.get(
    "/api/history/{serialno:path}",
    response_model=HistoryListResponse | HistoryRecordResponse,
)
def list_history(
    request: Request,
    serialno: str,
    limit: int = 50,
    offset: int = 0,
    mode: str | None = None,
) -> HistoryListResponse | HistoryRecordResponse:
    force_list = any(key in request.query_params for key in {"limit", "offset", "mode"})
    if _path_should_resolve_as_record(serialno, force_list=force_list):
        record_serialno, record_id = cast(
            tuple[str, str], _record_path_candidate(serialno)
        )
        return _get_history_record_response(record_serialno, record_id)
    return _list_history_response(serialno, limit, offset, mode)


@router.delete("/api/history/{serialno:path}")
def clear_history(serialno: str) -> dict[str, Any]:
    if _path_should_resolve_as_record(serialno):
        record_serialno, record_id = cast(
            tuple[str, str], _record_path_candidate(serialno)
        )
        return _delete_history_record(record_serialno, record_id)
    return _clear_history(serialno)
