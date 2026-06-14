"""In-memory reverse Android Agent registry, pairing, session state, and command routing."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import WebSocket

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.reverse_agent_protocol import (
    ReverseAgentCommand,
    ReverseAgentCommandResult,
)


def _default_time() -> float:
    return time.time()


@dataclass
class PairingRecord:
    pairing_id: str
    pairing_code: str
    created_at: float
    expires_at: float
    display_name: str | None = None
    claimed_at: float | None = None
    claimed_agent_id: str | None = None


@dataclass
class ReverseAgentRecord:
    agent_id: str
    pairing_id: str
    created_at: float
    last_seen_at: float
    token_hash: str
    display_name: str | None = None
    app_version: str | None = None
    platform: str = "android"
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_heartbeat_at: float | None = None
    connected_at: float | None = None
    disconnected_at: float | None = None
    session_id: str | None = None


@dataclass
class _PendingCommand:
    """In-flight command waiting for a command_result from the agent."""

    agent_id: str
    command_id: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    loop: asyncio.AbstractEventLoop | None = None
    result: ReverseAgentCommandResult | None = None
    cancelled: bool = False


class ReverseAgentRegistry:
    """Stores pairing records plus reverse-connection agent state and command routing."""

    def __init__(
        self,
        *,
        pairing_ttl_seconds: int = 600,
        heartbeat_timeout_seconds: int = 45,
        command_timeout_seconds: float = 30.0,
        claim_rate_limit_max_attempts: int = 10,
        claim_rate_limit_window_seconds: int = 60,
        stale_agent_ttl_seconds: int = 86400,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._pairing_ttl_seconds = pairing_ttl_seconds
        self._heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._command_timeout_seconds = command_timeout_seconds
        self._claim_rate_limit_max_attempts = claim_rate_limit_max_attempts
        self._claim_rate_limit_window_seconds = claim_rate_limit_window_seconds
        self._stale_agent_ttl_seconds = stale_agent_ttl_seconds
        self._time_fn = time_fn or _default_time
        self._lock = threading.RLock()
        self._pairings_by_id: dict[str, PairingRecord] = {}
        self._pairing_ids_by_code: dict[str, str] = {}
        self._agents: dict[str, ReverseAgentRecord] = {}

        # Active WebSocket sessions (agent_id -> WebSocket).
        # Access is protected by _lock but the WebSocket itself is asyncio-safe.
        self._sessions: dict[str, WebSocket] = {}

        # Pending commands keyed by command_id. Access must be under _lock.
        self._pending_commands: dict[str, _PendingCommand] = {}

        # Rate-limit state for pairing claim attempts (source_id -> deque of timestamps).
        self._claim_attempts: dict[str, deque[float]] = {}

    def create_pairing(self, *, display_name: str | None = None) -> PairingRecord:
        now = self._time_fn()
        with self._lock:
            self._cleanup_expired_pairings_locked(now)
            pairing_id = f"pair_{uuid.uuid4().hex}"
            pairing_code = self._generate_pairing_code_locked()
            record = PairingRecord(
                pairing_id=pairing_id,
                pairing_code=pairing_code,
                created_at=now,
                expires_at=now + self._pairing_ttl_seconds,
                display_name=display_name.strip() if display_name else None,
            )
            self._pairings_by_id[pairing_id] = record
            self._pairing_ids_by_code[pairing_code] = pairing_id
            return record

    def claim_pairing(
        self,
        *,
        pairing_code: str,
        display_name: str | None = None,
        app_version: str | None = None,
        platform: str | None = None,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> tuple[ReverseAgentRecord, str]:
        normalized_code = pairing_code.strip().upper()
        now = self._time_fn()
        source_id = source_id or "unknown"
        with self._lock:
            self._cleanup_expired_pairings_locked(now)
            self._enforce_claim_rate_limit_locked(source_id, now)
            pairing_id = self._pairing_ids_by_code.get(normalized_code)
            if pairing_id is None:
                raise ValueError("pairing_code_not_found")

            pairing = self._pairings_by_id[pairing_id]
            if pairing.claimed_agent_id is not None:
                raise ValueError("pairing_code_already_claimed")

            agent_token = secrets.token_urlsafe(32)
            agent_id = f"reverse_agent_{uuid.uuid4().hex}"
            record = ReverseAgentRecord(
                agent_id=agent_id,
                pairing_id=pairing.pairing_id,
                created_at=now,
                last_seen_at=now,
                token_hash=self._hash_token(agent_token),
                display_name=(display_name or pairing.display_name or "").strip()
                or None,
                app_version=app_version.strip() if app_version else None,
                platform=(platform or "android").strip() or "android",
                capabilities=sorted(
                    {cap.strip() for cap in capabilities or [] if cap.strip()}
                ),
                metadata=dict(metadata or {}),
            )

            pairing.claimed_at = now
            pairing.claimed_agent_id = agent_id
            self._agents[agent_id] = record
            return record, agent_token

    def authenticate_agent(
        self, *, agent_id: str, agent_token: str | None
    ) -> ReverseAgentRecord | None:
        if not agent_token:
            return None
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return None
            if not secrets.compare_digest(
                record.token_hash, self._hash_token(agent_token)
            ):
                return None
            return record

    def register_session(self, *, agent_id: str, websocket: WebSocket) -> None:
        """Register an active WebSocket session for an agent."""
        with self._lock:
            self._sessions[agent_id] = websocket

    @staticmethod
    def _set_pending_event(pending: _PendingCommand) -> None:
        """Signal a pending command event from any thread/loop safely."""
        if pending.loop is not None:
            pending.loop.call_soon_threadsafe(pending.event.set)
        else:
            pending.event.set()

    def unregister_session(self, *, agent_id: str) -> None:
        """Unregister a WebSocket session and fail pending commands."""
        with self._lock:
            self._sessions.pop(agent_id, None)
            pending = [
                cmd
                for cmd in self._pending_commands.values()
                if cmd.agent_id == agent_id
            ]
            for cmd in pending:
                cmd.cancelled = True
                cmd.result = ReverseAgentCommandResult.failure_result(
                    cmd.command_id, "agent_disconnected"
                )
                self._set_pending_event(cmd)

    def mark_session_connected(self, *, agent_id: str) -> ReverseAgentRecord:
        now = self._time_fn()
        with self._lock:
            record = self._agents[agent_id]
            record.connected_at = now
            record.last_seen_at = now
            record.session_id = f"ws_{uuid.uuid4().hex}"
            return record

    def mark_session_disconnected(self, *, agent_id: str) -> ReverseAgentRecord:
        now = self._time_fn()
        with self._lock:
            record = self._agents[agent_id]
            record.disconnected_at = now
            record.last_seen_at = now
            record.session_id = None
            return record

    def record_heartbeat(
        self,
        *,
        agent_id: str,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        app_version: str | None = None,
        display_name: str | None = None,
    ) -> ReverseAgentRecord:
        now = self._time_fn()
        with self._lock:
            record = self._agents[agent_id]
            record.last_seen_at = now
            record.last_heartbeat_at = now
            if capabilities is not None:
                record.capabilities = sorted(
                    {cap.strip() for cap in capabilities if cap.strip()}
                )
            if metadata:
                record.metadata.update(metadata)
            if app_version:
                record.app_version = app_version.strip()
            if display_name:
                record.display_name = display_name.strip()
            return record

    async def send_command(
        self,
        *,
        agent_id: str,
        command: ReverseAgentCommand,
        timeout_seconds: float | None = None,
    ) -> ReverseAgentCommandResult:
        """Send a command to an agent and wait for its result.

        Raises:
            ValueError: If the agent is not connected.
            TimeoutError: If the command times out.
        """
        timeout = timeout_seconds or self._command_timeout_seconds
        pending = _PendingCommand(
            agent_id=agent_id,
            command_id=command.command_id,
            loop=asyncio.get_running_loop(),
        )

        with self._lock:
            websocket = self._sessions.get(agent_id)
            record = self._agents.get(agent_id)
            if websocket is None or record is None:
                raise ValueError(f"reverse_agent_not_connected: {agent_id}")
            if self._connection_status_locked(record) == "stale":
                raise ValueError(f"reverse_agent_stale: {agent_id}")
            self._pending_commands[command.command_id] = pending

        try:
            await websocket.send_json(command.to_message())
            await asyncio.wait_for(pending.event.wait(), timeout=timeout)

            if pending.cancelled or pending.result is None:
                raise ValueError(f"command_failed_or_cancelled: {command.command_id}")

            return pending.result
        except asyncio.TimeoutError:
            logger.warning(
                f"Reverse agent command timed out: {command.command_id} "
                f"for agent {agent_id}"
            )
            raise TimeoutError(
                f"reverse_agent_command_timeout: {command.command_id}"
            ) from None
        finally:
            with self._lock:
                self._pending_commands.pop(command.command_id, None)

    def handle_command_result(
        self, *, agent_id: str, result: ReverseAgentCommandResult
    ) -> None:
        """Deliver a command_result from the agent to the waiting caller."""
        with self._lock:
            pending = self._pending_commands.get(result.command_id)
            if pending is None:
                logger.warning(
                    f"Received command_result for unknown/expired command "
                    f"{result.command_id} from agent {agent_id}"
                )
                return
            if pending.agent_id != agent_id:
                logger.warning(
                    f"Command {result.command_id} result from wrong agent "
                    f"{agent_id}, expected {pending.agent_id}"
                )
                return
            pending.result = result
            self._set_pending_event(pending)

    def is_agent_online(self, agent_id: str) -> bool:
        """Return True if the agent has an active WebSocket session."""
        with self._lock:
            return agent_id in self._sessions

    def list_agents(self) -> list[dict[str, Any]]:
        now = self._time_fn()
        with self._lock:
            self._cleanup_stale_agents_locked(now)
            return [
                self._snapshot_agent_locked(record) for record in self._agents.values()
            ]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return None
            return self._snapshot_agent_locked(record)

    def reset(self) -> None:
        with self._lock:
            self._pairings_by_id.clear()
            self._pairing_ids_by_code.clear()
            self._agents.clear()
            self._sessions.clear()
            self._pending_commands.clear()

    def heartbeat_interval_seconds(self) -> int:
        return max(5, self._heartbeat_timeout_seconds // 3)

    def _snapshot_agent_locked(self, record: ReverseAgentRecord) -> dict[str, Any]:
        return {
            "agent_id": record.agent_id,
            "pairing_id": record.pairing_id,
            "display_name": record.display_name,
            "platform": record.platform,
            "app_version": record.app_version,
            "capabilities": list(record.capabilities),
            "metadata": dict(record.metadata),
            "created_at": record.created_at,
            "last_seen_at": record.last_seen_at,
            "last_heartbeat_at": record.last_heartbeat_at,
            "connected_at": record.connected_at,
            "disconnected_at": record.disconnected_at,
            "connection_status": self._connection_status_locked(record),
        }

    def _connection_status_locked(self, record: ReverseAgentRecord) -> str:
        now = self._time_fn()
        if record.session_id is None:
            # Was it previously connected? Then it's offline. Otherwise just paired.
            if record.connected_at is not None:
                return "offline"
            return "paired"
        # Use the most recent heartbeat, connection, or seen timestamp to detect staleness.
        last_alive_at = (
            record.last_heartbeat_at or record.connected_at or record.last_seen_at
        )
        if now - last_alive_at > self._heartbeat_timeout_seconds:
            return "stale"
        return "connected"

    def remove_agent(self, *, agent_id: str) -> bool:
        """Remove an agent from the registry and disconnect its session."""
        with self._lock:
            record = self._agents.get(agent_id)
            if record is None:
                return False
            self._agents.pop(agent_id, None)
            # Keep the pairing mapping but mark it unclaimed so the code can be reused.
            if record.pairing_id:
                pairing = self._pairings_by_id.get(record.pairing_id)
                if pairing is not None:
                    pairing.claimed_at = None
                    pairing.claimed_agent_id = None
            websocket = self._sessions.pop(agent_id, None)
            pending = [
                cmd
                for cmd in self._pending_commands.values()
                if cmd.agent_id == agent_id
            ]
            for cmd in pending:
                cmd.cancelled = True
                cmd.result = ReverseAgentCommandResult.failure_result(
                    cmd.command_id, "agent_removed"
                )
                self._set_pending_event(cmd)
        if websocket is not None:
            try:
                asyncio.create_task(websocket.close(code=1000, reason="removed"))
            except Exception:
                logger.exception(
                    "Failed to close websocket for removed agent %s", agent_id
                )
        return True

    def _cleanup_expired_pairings_locked(self, now: float) -> None:
        expired_pairing_ids = [
            pairing_id
            for pairing_id, record in self._pairings_by_id.items()
            if record.claimed_agent_id is None and record.expires_at <= now
        ]
        for pairing_id in expired_pairing_ids:
            code = self._pairings_by_id[pairing_id].pairing_code
            self._pairings_by_id.pop(pairing_id, None)
            self._pairing_ids_by_code.pop(code, None)

    def _enforce_claim_rate_limit_locked(self, source_id: str, now: float) -> None:
        attempts = self._claim_attempts.setdefault(source_id, deque())
        cutoff = now - self._claim_rate_limit_window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= self._claim_rate_limit_max_attempts:
            raise ValueError("rate_limited")
        attempts.append(now)

    def _cleanup_stale_agents_locked(self, now: float) -> None:
        """Remove agents that have been offline longer than the stale TTL."""
        stale_agent_ids = [
            agent_id
            for agent_id, record in self._agents.items()
            if self._connection_status_locked(record) == "offline"
            and record.disconnected_at is not None
            and now - record.disconnected_at > self._stale_agent_ttl_seconds
        ]
        for agent_id in stale_agent_ids:
            self._agents.pop(agent_id, None)

    def _generate_pairing_code_locked(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if code not in self._pairing_ids_by_code:
                return code

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


_reverse_agent_registry = ReverseAgentRegistry()


def get_reverse_agent_registry() -> ReverseAgentRegistry:
    return _reverse_agent_registry
