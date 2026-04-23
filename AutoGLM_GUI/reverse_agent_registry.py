"""In-memory reverse Android Agent registry, pairing, and session state."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


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


class ReverseAgentRegistry:
    """Stores pairing records plus reverse-connection agent state."""

    def __init__(
        self,
        *,
        pairing_ttl_seconds: int = 600,
        heartbeat_timeout_seconds: int = 45,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._pairing_ttl_seconds = pairing_ttl_seconds
        self._heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._time_fn = time_fn or _default_time
        self._lock = threading.RLock()
        self._pairings_by_id: dict[str, PairingRecord] = {}
        self._pairing_ids_by_code: dict[str, str] = {}
        self._agents: dict[str, ReverseAgentRecord] = {}

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
    ) -> tuple[ReverseAgentRecord, str]:
        normalized_code = pairing_code.strip().upper()
        now = self._time_fn()
        with self._lock:
            self._cleanup_expired_pairings_locked(now)
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

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock:
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
            return "paired"
        if (
            record.last_heartbeat_at is not None
            and now - record.last_heartbeat_at > self._heartbeat_timeout_seconds
        ):
            return "stale"
        return "connected"

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
