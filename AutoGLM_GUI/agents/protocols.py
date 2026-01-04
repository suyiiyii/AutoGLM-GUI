"""Agent protocol and shared types.

This module defines the protocol (interface) that all agent implementations
must follow, as well as shared data types to avoid leaking third-party
dependencies to the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from phone_agent.agent import AgentConfig
    from phone_agent.model import ModelConfig


@dataclass
class StepResult:
    """Result of a single agent step.

    This is our own type definition to avoid exposing phone_agent.agent.StepResult
    directly to the API layer.
    """

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


class BaseAgent(Protocol):
    """Base protocol for all agent implementations.

    All concrete agent implementations (PhoneAgent, MAIAgent, etc.) must
    implement this interface.
    """

    agent_config: "AgentConfig"
    model_config: "ModelConfig"

    def run(self, task: str) -> str:
        """Execute a task end-to-end (blocking).

        Args:
            task: Task description in natural language

        Returns:
            Final result message
        """
        ...

    def step(self, task: str | None = None) -> StepResult:
        """Execute a single step of the task.

        Args:
            task: Optional task description (for first step)

        Returns:
            Result of this step
        """
        ...

    def reset(self) -> None:
        """Reset agent state for a new task."""
        ...

    def abort(self) -> None:
        """Abort the current running task.

        This method should be safe to call even if no task is running.
        """
        ...

    @property
    def step_count(self) -> int:
        """Get the number of steps executed in current task."""
        ...

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the conversation context."""
        ...

    @property
    def is_running(self) -> bool:
        """Check if the agent is currently executing a task."""
        ...
