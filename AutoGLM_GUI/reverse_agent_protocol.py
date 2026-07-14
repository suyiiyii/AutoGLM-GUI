"""Command protocol for reverse Android Agent connections.

This module defines the message types used between the AutoGLM-GUI server
and an Android Agent over the reverse WebSocket channel.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


ReverseAgentCommandType = Literal[
    "screenshot",
    "tap",
    "swipe",
    "type_text",
    "current_app",
]

_REVERSE_AGENT_COMMAND_TYPES = frozenset(
    ReverseAgentCommandType.__args__  # type: ignore[attr-defined]
)


@dataclass
class ReverseAgentCommand:
    """Server-to-agent command envelope."""

    command_id: str
    type: ReverseAgentCommandType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "command",
            "command_id": self.command_id,
            "command_type": self.type,
            "payload": self.payload,
        }

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> ReverseAgentCommand:
        command_type = message.get("command_type")
        if command_type not in _REVERSE_AGENT_COMMAND_TYPES:
            raise ValueError(
                f"unsupported_command_type: {command_type!r}; "
                f"expected one of {sorted(_REVERSE_AGENT_COMMAND_TYPES)}"
            )
        return cls(
            command_id=str(message.get("command_id") or uuid.uuid4().hex),
            type=command_type,  # type: ignore[arg-type]
            payload=dict(message.get("payload") or {}),
        )

    @classmethod
    def new(
        cls,
        command_type: ReverseAgentCommandType,
        payload: dict[str, Any] | None = None,
    ) -> ReverseAgentCommand:
        return cls(
            command_id=f"cmd_{uuid.uuid4().hex}",
            type=command_type,
            payload=dict(payload or {}),
        )


@dataclass
class ReverseAgentCommandResult:
    """Agent-to-server command execution result."""

    command_id: str
    success: bool
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float = field(default_factory=time.time)

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "command_result",
            "command_id": self.command_id,
            "success": self.success,
            "payload": self.payload,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> ReverseAgentCommandResult:
        return cls(
            command_id=str(message.get("command_id") or ""),
            success=bool(message.get("success", False)),
            payload=dict(message.get("payload") or {}),
            error=message.get("error") if message.get("error") else None,
            started_at=float(message.get("started_at") or time.time()),
            finished_at=float(message.get("finished_at") or time.time()),
        )

    @classmethod
    def success_result(
        cls,
        command_id: str,
        payload: dict[str, Any] | None = None,
        started_at: float | None = None,
    ) -> ReverseAgentCommandResult:
        now = time.time()
        return cls(
            command_id=command_id,
            success=True,
            payload=dict(payload or {}),
            error=None,
            started_at=started_at or now,
            finished_at=now,
        )

    @classmethod
    def failure_result(
        cls,
        command_id: str,
        error: str,
        started_at: float | None = None,
    ) -> ReverseAgentCommandResult:
        now = time.time()
        return cls(
            command_id=command_id,
            success=False,
            payload={},
            error=error,
            started_at=started_at or now,
            finished_at=now,
        )
