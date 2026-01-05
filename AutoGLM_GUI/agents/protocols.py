"""Agent protocol and shared types.

This module defines the protocol (interface) that all agent implementations
must follow.
"""

from __future__ import annotations

from typing import Any, Protocol

from AutoGLM_GUI.config import StepResult


class BaseAgent(Protocol):
    """Base protocol for all agent implementations.

    All concrete agent implementations (PhoneAgent, MAIAgent, etc.) must
    implement this interface.

    Note: agent_config and model_config are not declared here to avoid
    Protocol invariance issues. Implementations should provide these attributes.
    """

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
