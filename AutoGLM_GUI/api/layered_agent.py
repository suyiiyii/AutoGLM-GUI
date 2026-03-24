"""Compatibility API for layered agent mode backed by the task system."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from AutoGLM_GUI.layered_agent_service import reset_session as reset_layered_session
from AutoGLM_GUI.task_manager import task_manager
from AutoGLM_GUI.task_store import TERMINAL_TASK_STATUSES, task_store

router = APIRouter()


class LayeredAgentRequest(BaseModel):
    """Request for layered agent chat."""

    message: str
    device_id: str | None = None
    session_id: str | None = None


class AbortSessionRequest(BaseModel):
    """Request for aborting a running session."""

    session_id: str


class ResetSessionRequest(BaseModel):
    """Request for resetting a session."""

    session_id: str


def _resolve_device_serial(device_id: str) -> str:
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    return device_manager.get_serial_by_device_id(device_id) or device_id


async def _resolve_layered_session(
    session_id: str,
) -> dict[str, object] | None:
    direct_session = await task_manager.get_session(session_id)
    if (
        direct_session is not None
        and str(direct_session.get("kind")) == "chat"
        and str(direct_session.get("mode")) == "layered"
        and str(direct_session.get("status")) == "open"
    ):
        return direct_session

    device_serial = _resolve_device_serial(session_id)
    return await asyncio.to_thread(
        task_store.get_latest_open_chat_session,
        device_id=session_id,
        device_serial=device_serial,
        mode="layered",
    )


async def _get_or_create_compat_session(
    request: LayeredAgentRequest,
) -> dict[str, object]:
    if request.session_id:
        session = await _resolve_layered_session(request.session_id)
        if session is not None:
            return session

    legacy_device_id = request.device_id or request.session_id
    if legacy_device_id:
        return await task_manager.get_or_create_legacy_chat_session(
            device_id=legacy_device_id,
            device_serial=_resolve_device_serial(legacy_device_id),
            mode="layered",
        )

    raise ValueError("device_id is required when no layered task session exists")


def _compat_sse_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_type == "tool_call":
        return {
            "type": "tool_call",
            "tool_name": payload.get("tool_name", "unknown"),
            "tool_args": payload.get("tool_args", {}),
        }
    if event_type == "tool_result":
        return {
            "type": "tool_result",
            "tool_name": payload.get("tool_name", "unknown"),
            "result": payload.get("result", ""),
        }
    if event_type == "message":
        return {
            "type": "message",
            "content": payload.get("content", ""),
        }
    if event_type == "done":
        return {
            "type": "done",
            "content": payload.get("content", payload.get("message", "")),
            "success": payload.get("success", True),
        }
    if event_type == "cancelled":
        return {
            "type": "error",
            "message": payload.get("message", "Task cancelled by user"),
        }
    return {
        "type": "error",
        "message": payload.get("message", "Task failed"),
    }


async def _stream_layered_task(task_id: str) -> AsyncGenerator[str, None]:
    last_seq = 0
    while True:
        events = await asyncio.to_thread(
            task_store.list_task_events,
            task_id,
            after_seq=last_seq,
        )
        for event in events:
            last_seq = int(event["seq"])
            event_type = str(event["event_type"])
            if event_type == "status":
                continue

            compat_payload = _compat_sse_payload(event_type, dict(event["payload"]))
            yield f"data: {json.dumps(compat_payload, ensure_ascii=False)}\n\n"

        current_task = await asyncio.to_thread(task_store.get_task, task_id)
        if (
            current_task is None or current_task["status"] in TERMINAL_TASK_STATUSES
        ) and not events:
            break
        await asyncio.sleep(0.2)


@router.post("/api/layered-agent/chat")
async def layered_agent_chat(request: LayeredAgentRequest) -> StreamingResponse:
    session = await _get_or_create_compat_session(request)
    task = await task_manager.submit_chat_task(
        session_id=str(session["id"]),
        device_id=str(session["device_id"]),
        device_serial=str(session["device_serial"]),
        message=request.message,
    )
    return StreamingResponse(
        _stream_layered_task(str(task["id"])),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/layered-agent/abort")
async def abort_session(request: AbortSessionRequest) -> dict[str, Any]:
    session = await _resolve_layered_session(request.session_id)
    if session is None:
        return {
            "success": False,
            "message": f"No active run found for session {request.session_id}",
        }

    active_task = await asyncio.to_thread(
        task_store.get_latest_active_session_task,
        str(session["id"]),
    )
    if active_task is None:
        return {
            "success": False,
            "message": f"No active run found for session {request.session_id}",
        }

    await task_manager.cancel_task(str(active_task["id"]))
    return {
        "success": True,
        "message": f"Session {request.session_id} abort signal sent",
    }


@router.post("/api/layered-agent/reset")
async def reset_session(request: ResetSessionRequest) -> dict[str, Any]:
    session = await _resolve_layered_session(request.session_id)
    if session is None:
        return {
            "success": True,
            "message": f"Session {request.session_id} not found (already empty)",
        }

    active_task = await asyncio.to_thread(
        task_store.get_latest_active_session_task,
        str(session["id"]),
    )
    if active_task is not None:
        await task_manager.cancel_task(str(active_task["id"]))
        await task_manager.wait_for_task(str(active_task["id"]))

    reset_layered_session(str(session["id"]))
    await task_manager.archive_session(str(session["id"]))
    return {
        "success": True,
        "message": f"Session {request.session_id} cleared",
    }
