"""History API routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from AutoGLM_GUI.history_manager import history_manager
from AutoGLM_GUI.models.history import ConversationRecord
from AutoGLM_GUI.schemas import (
    HistoryListResponse,
    HistoryRecordResponse,
    MessageRecordResponse,
    StepTimingSummaryResponse,
    TraceSummaryResponse,
)

router = APIRouter()


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


@router.get("/api/history/{serialno}", response_model=HistoryListResponse)
def list_history(
    serialno: str, limit: int = 50, offset: int = 0
) -> HistoryListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")

    records = history_manager.list_records(serialno, limit=limit, offset=offset)
    total = history_manager.get_total_count(serialno)

    return HistoryListResponse(
        records=[_build_history_record_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/history/{serialno}/{record_id}", response_model=HistoryRecordResponse)
def get_history_record(serialno: str, record_id: str) -> HistoryRecordResponse:
    record = history_manager.get_record(serialno, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    return _build_history_record_response(record)


@router.delete("/api/history/{serialno}/{record_id}")
def delete_history_record(serialno: str, record_id: str) -> dict[str, Any]:
    success = history_manager.delete_record(serialno, record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "message": "Record deleted"}


@router.delete("/api/history/{serialno}")
def clear_history(serialno: str) -> dict[str, Any]:
    history_manager.clear_device_history(serialno)
    return {"success": True, "message": f"History cleared for {serialno}"}
