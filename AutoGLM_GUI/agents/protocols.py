from __future__ import annotations

from typing import Any, Protocol

from AutoGLM_GUI.config import AgentConfig, ModelConfig, StepResult


class BaseAgent(Protocol):
    model_config: ModelConfig
    agent_config: AgentConfig

    def run(self, task: str) -> str: ...

    def step(self, task: str | None = None) -> StepResult: ...

    def reset(self) -> None: ...

    def abort(self) -> None: ...

    @property
    def step_count(self) -> int: ...

    @property
    def context(self) -> list[dict[str, Any]]: ...

    @property
    def is_running(self) -> bool: ...
