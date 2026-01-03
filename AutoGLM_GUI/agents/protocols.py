from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from phone_agent.agent import AgentConfig, StepResult
    from phone_agent.model import ModelConfig


class BaseAgent(Protocol):
    agent_config: "AgentConfig"
    model_config: "ModelConfig"

    def run(self, task: str) -> str: ...
    def step(self, task: str | None = None) -> "StepResult": ...
    def reset(self) -> None: ...

    @property
    def step_count(self) -> int: ...

    @property
    def context(self) -> list[dict[str, Any]]: ...
