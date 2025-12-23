"""Shared runtime state for the AutoGLM-GUI API."""

from __future__ import annotations

import asyncio
from typing import Any
from typing import TYPE_CHECKING

from AutoGLM_GUI.logger import logger
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

if TYPE_CHECKING:
    from AutoGLM_GUI.platforms.adb.video.scrcpy_stream import ScrcpyStreamer
    from phone_agent.agent_ios import IOSAgentConfig

# Agent instances keyed by device_id
agents: dict[str, Any] = {}
# Cached configs to rebuild agents on reset
agent_configs: dict[str, tuple[ModelConfig, AgentConfig | "IOSAgentConfig"]] = {}
agent_types: dict[str, str] = {}
known_device_types: dict[str, str] = {}

# Scrcpy streaming per device
scrcpy_streamers: dict[str, "ScrcpyStreamer"] = {}
scrcpy_locks: dict[str, asyncio.Lock] = {}


def non_blocking_takeover(message: str) -> None:
    """Log takeover requests without blocking for console input."""
    logger.warning(f"Takeover requested: {message}")
