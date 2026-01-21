"""Shared runtime state for the AutoGLM-GUI API.

NOTE: Agent instances and configurations are now managed internally
by PhoneAgentManager singleton. This module only contains:
- scrcpy_streamers: Video streaming state per device
- scrcpy_locks: Async locks for stream management
- non_blocking_takeover: Takeover callback handler

See PhoneAgentManager (phone_agent_manager.py) for agent lifecycle management.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from AutoGLM_GUI.logger import logger

if TYPE_CHECKING:
    from AutoGLM_GUI.scrcpy_stream import ScrcpyStreamer

# Scrcpy streaming per device
scrcpy_streamers: dict[str, "ScrcpyStreamer"] = {}
scrcpy_locks: dict[str, asyncio.Lock] = {}


def non_blocking_takeover(message: str) -> None:
    """Log takeover requests without blocking for console input."""
    logger.warning(f"Takeover requested: {message}")
