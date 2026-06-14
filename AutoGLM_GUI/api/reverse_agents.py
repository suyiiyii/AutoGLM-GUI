"""Reverse Android Agent pairing, registry, websocket session, and command routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.reverse_agent_protocol import (
    ReverseAgentCommand,
    ReverseAgentCommandResult,
)
from AutoGLM_GUI.reverse_agent_registry import get_reverse_agent_registry
from AutoGLM_GUI.schemas import (
    ReverseAgentCommandRequest,
    ReverseAgentCommandResponse,
    ReverseAgentHeartbeatAck,
    ReverseAgentInfo,
    ReverseAgentPairingClaimRequest,
    ReverseAgentPairingClaimResponse,
    ReverseAgentPairingCreateRequest,
    ReverseAgentPairingCreateResponse,
    ReverseAgentRegistryListResponse,
    ReverseAgentSessionReady,
)

router = APIRouter()


@router.post(
    "/api/reverse_agents/pairings",
    response_model=ReverseAgentPairingCreateResponse,
)
def create_pairing(
    request: ReverseAgentPairingCreateRequest,
) -> ReverseAgentPairingCreateResponse:
    registry = get_reverse_agent_registry()
    pairing = registry.create_pairing(display_name=request.display_name)
    return ReverseAgentPairingCreateResponse(
        pairing_id=pairing.pairing_id,
        pairing_code=pairing.pairing_code,
        created_at=pairing.created_at,
        expires_at=pairing.expires_at,
        heartbeat_interval_seconds=registry.heartbeat_interval_seconds(),
    )


@router.post(
    "/api/reverse_agents/pairings/claim",
    response_model=ReverseAgentPairingClaimResponse,
)
def claim_pairing(
    request: ReverseAgentPairingClaimRequest,
    http_request: Request,
) -> ReverseAgentPairingClaimResponse:
    registry = get_reverse_agent_registry()
    source_id = http_request.client.host if http_request.client else "unknown"
    try:
        agent, agent_token = registry.claim_pairing(
            pairing_code=request.pairing_code,
            display_name=request.display_name,
            app_version=request.app_version,
            platform=request.platform,
            capabilities=request.capabilities,
            metadata=request.metadata,
            source_id=source_id,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "pairing_code_not_found":
            raise HTTPException(status_code=404, detail=detail) from exc
        if detail == "rate_limited":
            raise HTTPException(status_code=429, detail=detail) from exc
        raise HTTPException(status_code=409, detail=detail) from exc

    return ReverseAgentPairingClaimResponse(
        agent_id=agent.agent_id,
        agent_token=agent_token,
        pairing_id=agent.pairing_id,
        websocket_path=f"/api/reverse_agents/agents/{agent.agent_id}/ws",
        heartbeat_interval_seconds=registry.heartbeat_interval_seconds(),
    )


@router.get(
    "/api/reverse_agents/registry", response_model=ReverseAgentRegistryListResponse
)
def list_registry() -> ReverseAgentRegistryListResponse:
    registry = get_reverse_agent_registry()
    return ReverseAgentRegistryListResponse(
        agents=[
            ReverseAgentInfo.model_validate(agent) for agent in registry.list_agents()
        ]
    )


@router.get("/api/reverse_agents/registry/{agent_id}", response_model=ReverseAgentInfo)
def get_registry_agent(agent_id: str) -> ReverseAgentInfo:
    registry = get_reverse_agent_registry()
    agent = registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="reverse_agent_not_found")
    return ReverseAgentInfo.model_validate(agent)


@router.delete("/api/reverse_agents/registry/{agent_id}")
def delete_registry_agent(agent_id: str) -> dict[str, bool]:
    registry = get_reverse_agent_registry()
    removed = registry.remove_agent(agent_id=agent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="reverse_agent_not_found")
    return {"success": True}


@router.post(
    "/api/reverse_agents/agents/{agent_id}/commands",
    response_model=ReverseAgentCommandResponse,
)
async def send_command_to_agent(
    agent_id: str,
    request: ReverseAgentCommandRequest,
) -> ReverseAgentCommandResponse:
    """Send a command to a reverse Android Agent and return its execution result."""
    registry = get_reverse_agent_registry()

    agent = registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="reverse_agent_not_found")

    command = ReverseAgentCommand.new(
        command_type=request.command_type,
        payload=request.payload,
    )

    try:
        result = await registry.send_command(
            agent_id=agent_id,
            command=command,
            timeout_seconds=request.timeout_seconds,
        )
    except ValueError as exc:
        error_message = str(exc)
        if "reverse_agent_not_connected" in error_message:
            raise HTTPException(status_code=503, detail=error_message) from exc
        if "reverse_agent_stale" in error_message:
            raise HTTPException(status_code=503, detail=error_message) from exc
        if "rate_limited" in error_message:
            raise HTTPException(status_code=429, detail=error_message) from exc
        raise HTTPException(status_code=400, detail=error_message) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"reverse_agent_command_timeout: {command.command_id}",
        ) from exc

    return ReverseAgentCommandResponse(
        command_id=result.command_id,
        success=result.success,
        payload=result.payload,
        error=result.error,
        started_at=result.started_at,
        finished_at=result.finished_at,
    )


@router.websocket("/api/reverse_agents/agents/{agent_id}/ws")
async def reverse_agent_session(websocket: WebSocket, agent_id: str) -> None:
    registry = get_reverse_agent_registry()
    agent = registry.authenticate_agent(
        agent_id=agent_id,
        agent_token=websocket.query_params.get("token"),
    )
    if agent is None:
        await websocket.close(code=4403, reason="Invalid reverse agent token")
        return

    await websocket.accept()
    registry.mark_session_connected(agent_id=agent_id)
    registry.register_session(agent_id=agent_id, websocket=websocket)

    try:
        from AutoGLM_GUI.device_manager import DeviceManager

        device_manager = DeviceManager.get_instance()
        device_manager.register_reverse_agent(
            agent_id=agent_id,
            display_name=agent.display_name,
            model=agent.metadata.get("model") if agent.metadata else None,
        )
    except Exception:
        logger.exception("Failed to register reverse agent in DeviceManager")

    try:
        await websocket.send_json(
            ReverseAgentSessionReady(
                type="session_ready",
                agent_id=agent_id,
                heartbeat_interval_seconds=registry.heartbeat_interval_seconds(),
            ).model_dump()
        )

        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                return

            message_type = message.get("type")
            if message_type == "heartbeat":
                updated = registry.record_heartbeat(
                    agent_id=agent_id,
                    capabilities=_parse_capabilities(message.get("capabilities")),
                    metadata=_parse_metadata(message.get("metadata")),
                    app_version=_parse_optional_str(message.get("app_version")),
                    display_name=_parse_optional_str(message.get("display_name")),
                )
                connection_status = registry.get_agent(agent_id)
                status_value = (
                    connection_status.get("connection_status", "connected")
                    if connection_status
                    else "connected"
                )
                await websocket.send_json(
                    ReverseAgentHeartbeatAck(
                        type="heartbeat_ack",
                        agent_id=agent_id,
                        server_time=updated.last_seen_at,
                        connection_status=status_value,
                    ).model_dump()
                )
            elif message_type == "command_result":
                try:
                    result = ReverseAgentCommandResult.from_message(message)
                    registry.handle_command_result(agent_id=agent_id, result=result)
                except Exception:
                    logger.exception(
                        "Failed to process command_result from agent %s", agent_id
                    )
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unsupported reverse agent message type: {message_type}",
                    }
                )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
    except Exception:
        logger.exception("Reverse agent websocket session failed")
        await websocket.close(code=1011, reason="Reverse agent session failed")
    finally:
        registry.unregister_session(agent_id=agent_id)
        registry.mark_session_disconnected(agent_id=agent_id)
        try:
            from AutoGLM_GUI.device_manager import DeviceManager

            device_manager = DeviceManager.get_instance()
            device_manager.unregister_reverse_agent(agent_id=agent_id)
        except Exception:
            logger.exception("Failed to unregister reverse agent from DeviceManager")


def _parse_capabilities(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _parse_metadata(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _parse_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
