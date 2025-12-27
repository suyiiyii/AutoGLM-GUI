"""Shared runtime state for the AutoGLM-GUI API."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from AutoGLM_GUI.logger import logger
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

if TYPE_CHECKING:
    from AutoGLM_GUI.scrcpy_stream import ScrcpyStreamer
    from phone_agent import PhoneAgent

# Agent instances keyed by device_id
#
# IMPORTANT: Managed by PhoneAgentManager (AutoGLM_GUI/phone_agent_manager.py)
# - Do NOT directly modify these dictionaries
# - Use PhoneAgentManager.get_instance() for all agent operations
#
# device_id changes when connection method changes
# (e.g., USB "ABC123" → WiFi "192.168.1.100:5555")
#
# This means the same physical device may have different device_ids:
#   - USB connection: device_id = hardware serial (e.g., "ABC123DEF")
#   - WiFi connection: device_id = IP:port (e.g., "192.168.1.100:5555")
#   - mDNS connection: device_id = service name (e.g., "adb-ABC123._adb-tls-connect._tcp")
#
# DeviceManager tracks devices by hardware serial and maintains
# device_id ↔ serial mapping. Use PhoneAgentManager.find_agent_by_serial()
# to find agents when device_id changes.
#
# See CLAUDE.md "Device Identification" section for details.
agents: dict[str, "PhoneAgent"] = {}

# Cached configs to rebuild agents on reset
# Keyed by device_id (same semantics as agents dict)
# IMPORTANT: Managed by PhoneAgentManager - do NOT modify directly
agent_configs: dict[str, tuple[ModelConfig, AgentConfig]] = {}

# Scrcpy streaming per device
scrcpy_streamers: dict[str, "ScrcpyStreamer"] = {}
scrcpy_locks: dict[str, asyncio.Lock] = {}


def non_blocking_takeover(message: str) -> None:
    """Log takeover requests without blocking for console input."""
    logger.warning(f"Takeover requested: {message}")
