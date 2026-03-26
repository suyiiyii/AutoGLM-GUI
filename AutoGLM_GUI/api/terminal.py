"""Web terminal API routes."""

from __future__ import annotations

import asyncio
import ipaddress
import os
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from AutoGLM_GUI.adb_terminal_service import terminal_session_manager
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.schemas import (
    TerminalSessionCloseResponse,
    TerminalSessionCreateRequest,
    TerminalSessionCreateResponse,
    TerminalSessionResponse,
)

router = APIRouter()


def _server_host() -> str:
    return os.getenv("AUTOGLM_SERVER_HOST", "127.0.0.1").strip().lower()


def _terminal_explicitly_enabled() -> bool:
    return os.getenv("AUTOGLM_ENABLE_WEB_TERMINAL", "0").strip() == "1"


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip().lower()
    if normalized in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _is_terminal_feature_enabled() -> bool:
    return _is_loopback_host(_server_host()) or _terminal_explicitly_enabled()


def _get_allowed_origins() -> list[str]:
    cors_origins_str = os.getenv("AUTOGLM_CORS_ORIGINS", "http://localhost:3000")
    if cors_origins_str == "*":
        return ["*"]
    return [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]


def _same_origin_from_websocket(websocket: WebSocket) -> str:
    scheme = "https" if websocket.url.scheme == "wss" else "http"
    return f"{scheme}://{websocket.headers.get('host', '')}"


def _is_allowed_origin(origin: str | None, websocket: WebSocket) -> bool:
    if not origin:
        return _is_loopback_host(websocket.client.host if websocket.client else None)

    allowed_origins = _get_allowed_origins()
    if "*" in allowed_origins:
        return True

    return origin in allowed_origins or origin == _same_origin_from_websocket(websocket)


def _require_terminal_enabled() -> None:
    if not _is_terminal_feature_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Web terminal is disabled for non-local hosts. "
                "Set AUTOGLM_ENABLE_WEB_TERMINAL=1 to enable it explicitly."
            ),
        )


def _require_local_request(request: Request) -> None:
    if _terminal_explicitly_enabled():
        return
    client_host = request.client.host if request.client else None
    if not _is_loopback_host(client_host):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Web terminal is only available from localhost by default.",
        )


def _require_authenticated_session(session_id: str, session_token: str | None) -> Any:
    session = terminal_session_manager.authenticate_session(session_id, session_token)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid terminal session token",
        )
    return session


@router.post("/api/terminal/sessions", response_model=TerminalSessionCreateResponse)
async def create_terminal_session(
    request: Request,
    terminal_request: TerminalSessionCreateRequest,
) -> TerminalSessionCreateResponse:
    """Create a new interactive terminal session."""
    _require_terminal_enabled()
    _require_local_request(request)

    try:
        session, session_token = await terminal_session_manager.create_session(
            cwd=terminal_request.cwd,
            command=terminal_request.command,
            created_by=request.client.host if request.client else None,
            origin=request.headers.get("origin"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to create terminal session")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TerminalSessionCreateResponse.model_validate(
        {
            **session.to_response(),
            "session_token": session_token,
        }
    )


@router.get(
    "/api/terminal/sessions/{session_id}", response_model=TerminalSessionResponse
)
async def get_terminal_session(
    request: Request,
    session_id: str,
    token: str | None = Query(default=None),
) -> TerminalSessionResponse:
    """Return terminal session metadata."""
    _require_terminal_enabled()
    _require_local_request(request)
    session = _require_authenticated_session(session_id, token)
    return TerminalSessionResponse.model_validate(session.to_response())


@router.delete(
    "/api/terminal/sessions/{session_id}",
    response_model=TerminalSessionCloseResponse,
)
async def close_terminal_session(
    request: Request,
    session_id: str,
    token: str | None = Query(default=None),
) -> TerminalSessionCloseResponse:
    """Close a terminal session."""
    _require_terminal_enabled()
    _require_local_request(request)
    _require_authenticated_session(session_id, token)

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
    if not _is_terminal_feature_enabled():
        await websocket.close(
            code=4403,
            reason="Web terminal is disabled for non-local hosts",
        )
        return

    if not _terminal_explicitly_enabled():
        client_host = websocket.client.host if websocket.client else None
        if not _is_loopback_host(client_host):
            await websocket.close(code=4403, reason="Web terminal is localhost-only")
            return

    if not _is_allowed_origin(websocket.headers.get("origin"), websocket):
        await websocket.close(code=4403, reason="Origin is not allowed")
        return

    session = terminal_session_manager.authenticate_session(
        session_id, websocket.query_params.get("token")
    )
    if session is None:
        await websocket.close(code=4403, reason="Invalid terminal session token")
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
