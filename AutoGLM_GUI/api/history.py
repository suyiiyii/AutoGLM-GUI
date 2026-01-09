"""History API routes."""

from fastapi import APIRouter, HTTPException

from AutoGLM_GUI.history_manager import history_manager
from AutoGLM_GUI.schemas import (
    HistoryListResponse,
    HistoryRecordResponse,
    MessageRecordResponse,
)

router = APIRouter()


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
        records=[
            HistoryRecordResponse(
                id=r.id,
                task_text=r.task_text,
                final_message=r.final_message,
                success=r.success,
                steps=r.steps,
                start_time=r.start_time.isoformat(),
                end_time=r.end_time.isoformat() if r.end_time else None,
                duration_ms=r.duration_ms,
                source=r.source,
                source_detail=r.source_detail,
                error_message=r.error_message,
                messages=[
                    MessageRecordResponse(
                        role=m.role,
                        content=m.content,
                        timestamp=m.timestamp.isoformat(),
                        thinking=m.thinking,
                        action=m.action,
                        step=m.step,
                    )
                    for m in r.messages
                ],
            )
            for r in records
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/history/{serialno}/{record_id}", response_model=HistoryRecordResponse)
def get_history_record(serialno: str, record_id: str) -> HistoryRecordResponse:
    record = history_manager.get_record(serialno, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

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
        messages=[
            MessageRecordResponse(
                role=m.role,
                content=m.content,
                timestamp=m.timestamp.isoformat(),
                thinking=m.thinking,
                action=m.action,
                step=m.step,
            )
            for m in record.messages
        ],
    )


@router.delete("/api/history/{serialno}/{record_id}")
def delete_history_record(serialno: str, record_id: str) -> dict:
    success = history_manager.delete_record(serialno, record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "message": "Record deleted"}


@router.delete("/api/history/{serialno}")
def clear_history(serialno: str) -> dict:
    history_manager.clear_device_history(serialno)
    return {"success": True, "message": f"History cleared for {serialno}"}
