"""MAI Agent - Internal implementation.

This module co-locates all MAI-specific code:
- InternalMAIAgent: The main agent implementation
- MAIParser: XML+JSON format parser with coordinate conversion (0-999 to 0-1000)
- MAI_MOBILE_SYSTEM_PROMPT: System prompt for Chinese environments
- TrajMemory, TrajStep: Trajectory memory for multi-step tasks

Design notes:
- MAI uses 0-999 coordinate system (normalized internally)
- Supports multi-image history context (configurable via history_n)
- Chinese-optimized prompts for domestic app scenarios
- Internal implementation replacing third-party mai_agent dependency
"""

from .agent import InternalMAIAgent
from .parser import MAIParser, MAIParseError
from .prompts import MAI_MOBILE_SYSTEM_PROMPT
from .traj_memory import TrajMemory, TrajStep

__all__ = [
    "InternalMAIAgent",
    "MAIParser",
    "MAIParseError",
    "MAI_MOBILE_SYSTEM_PROMPT",
    "TrajMemory",
    "TrajStep",
]
