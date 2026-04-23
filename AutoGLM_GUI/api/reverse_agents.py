"""Reverse Android Agent pairing, registry, and websocket session routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.reverse_agent_registry import get_reverse_agent_registry
from AutoGLM_GUI.schemas import (
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
) -> ReverseAgentPairingClaimResponse:
    registry = get_reverse_agent_registry()
    try:
        agent, agent_token = registry.claim_pairing(
            pairing_code=request.pairing_code,
            display_name=request.display_name,
            app_version=request.app_version,
            platform=request.platform,
            capabilities=request.capabilities,
            metadata=request.metadata,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "pairing_code_not_found":
            raise HTTPException(status_code=404, detail=detail) from exc
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
                await websocket.send_json(
                    ReverseAgentHeartbeatAck(
                        type="heartbeat_ack",
                        agent_id=agent_id,
                        server_time=updated.last_seen_at,
                        connection_status="connected",
                    ).model_dump()
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
        registry.mark_session_disconnected(agent_id=agent_id)


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
