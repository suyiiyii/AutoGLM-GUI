"""Web terminal API routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from AutoGLM_GUI.adb_terminal_service import terminal_session_manager
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.schemas import (
    TerminalSessionCloseResponse,
    TerminalSessionCreateRequest,
    TerminalSessionResponse,
)

router = APIRouter()


@router.post("/api/terminal/sessions", response_model=TerminalSessionResponse)
async def create_terminal_session(
    request: TerminalSessionCreateRequest,
) -> TerminalSessionResponse:
    """Create a new interactive terminal session."""
    try:
        session = await terminal_session_manager.create_session(
            cwd=request.cwd,
            command=request.command,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to create terminal session")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TerminalSessionResponse.model_validate(session.to_response())


@router.get(
    "/api/terminal/sessions/{session_id}", response_model=TerminalSessionResponse
)
async def get_terminal_session(session_id: str) -> TerminalSessionResponse:
    """Return terminal session metadata."""
    session = terminal_session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Terminal session not found")

    return TerminalSessionResponse.model_validate(session.to_response())


@router.delete(
    "/api/terminal/sessions/{session_id}",
    response_model=TerminalSessionCloseResponse,
)
async def close_terminal_session(session_id: str) -> TerminalSessionCloseResponse:
    """Close a terminal session."""
    closed = await terminal_session_manager.close_session(session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Terminal session not found")

    return TerminalSessionCloseResponse(
        success=True,
        message="Terminal session closed",
        session_id=session_id,
    )


@router.websocket("/api/terminal/sessions/{session_id}/stream")
async def terminal_session_stream(websocket: WebSocket, session_id: str) -> None:
    """Bidirectional terminal transport over WebSocket."""
    session = terminal_session_manager.get_session(session_id)
    if session is None:
        await websocket.close(code=4404, reason="Terminal session not found")
        return

    await websocket.accept()

    queue, backlog = session.subscribe()
    try:
        for event in backlog:
            await websocket.send_json(event)

        sender_task = asyncio.create_task(_send_terminal_events(websocket, queue))
        receiver_task = asyncio.create_task(_receive_terminal_input(websocket, session))

        done, pending = await asyncio.wait(
            {sender_task, receiver_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.gather(*done, return_exceptions=True)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
    finally:
        session.unsubscribe(queue)


async def _send_terminal_events(
    websocket: WebSocket, queue: asyncio.Queue[dict[str, Any]]
) -> None:
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


async def _receive_terminal_input(websocket: WebSocket, session: Any) -> None:
    try:
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                return

            message_type = message.get("type")
            if message_type == "input":
                await session.write(str(message.get("data", "")))
            elif message_type == "resize":
                await session.resize(
                    int(message.get("cols", 80)),
                    int(message.get("rows", 24)),
                )
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unsupported terminal message type: {message_type}",
                    }
                )
    except asyncio.CancelledError:
        return
