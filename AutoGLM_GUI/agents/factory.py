"""Agent factory for creating different agent implementations.

This module provides a factory pattern + registry for creating agents,
making it easy to add new agent types without modifying existing code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict

from AutoGLM_GUI.logger import logger

if TYPE_CHECKING:
    from phone_agent.agent import AgentConfig, StepResult
    from phone_agent.model import ModelConfig

    # Base agent interface (protocol)
    class BaseAgent:
        """Common interface that all agents must implement."""

        def run(self, task: str) -> str: ...
        def step(self, task: str | None) -> StepResult: ...
        def reset(self) -> None: ...
        @property
        def step_count(self) -> int: ...


# Agent registry: agent_type -> (creator_function, config_schema)
AGENT_REGISTRY: Dict[str, Callable] = {}


def register_agent(
    agent_type: str,
    creator: Callable,
) -> None:
    """
    Register a new agent type.

    Args:
        agent_type: Unique identifier for the agent type (e.g., "glm", "mai")
        creator: Function that creates the agent instance.
                  Signature: (model_config, agent_config, agent_specific_config, callbacks) -> BaseAgent

    Example:
        >>> def create_mai_agent(model_config, agent_config, mai_config, callbacks):
        >>>     return MAIAgentAdapter(...)
        >>>
        >>> register_agent("mai", create_mai_agent)
    """
    if agent_type in AGENT_REGISTRY:
        logger.warning(f"Agent type '{agent_type}' already registered, overwriting")

    AGENT_REGISTRY[agent_type] = creator
    logger.info(f"Registered agent type: {agent_type}")


def create_agent(
    agent_type: str,
    model_config: "ModelConfig",
    agent_config: "AgentConfig",
    agent_specific_config: dict[str, Any],
    takeover_callback: Callable | None = None,
    confirmation_callback: Callable | None = None,
) -> "BaseAgent":
    """
    Create an agent instance using the factory pattern.

    Args:
        agent_type: Type of agent to create (e.g., "glm", "mai")
        model_config: Model configuration
        agent_config: Agent configuration
        agent_specific_config: Agent-specific configuration (e.g., MAIConfig fields)
        takeover_callback: Takeover callback
        confirmation_callback: Confirmation callback

    Returns:
        Agent instance implementing BaseAgent interface

    Raises:
        ValueError: If agent_type is not registered
    """
    if agent_type not in AGENT_REGISTRY:
        available = ", ".join(AGENT_REGISTRY.keys())
        raise ValueError(
            f"Unknown agent type: '{agent_type}'. Available types: {available}"
        )

    creator = AGENT_REGISTRY[agent_type]

    try:
        agent = creator(
            model_config=model_config,
            agent_config=agent_config,
            agent_specific_config=agent_specific_config,
            takeover_callback=takeover_callback,
            confirmation_callback=confirmation_callback,
        )
        logger.debug(f"Created agent of type '{agent_type}'")
        return agent
    except Exception as e:
        logger.error(f"Failed to create agent of type '{agent_type}': {e}")
        raise


def list_agent_types() -> list[str]:
    """Get list of registered agent types."""
    return list(AGENT_REGISTRY.keys())


def is_agent_type_registered(agent_type: str) -> bool:
    """Check if an agent type is registered."""
    return agent_type in AGENT_REGISTRY


# ==================== Built-in Agent Creators ====================


def _create_phone_agent(
    model_config: "ModelConfig",
    agent_config: "AgentConfig",
    agent_specific_config: dict[str, Any],
    takeover_callback: Callable | None = None,
    confirmation_callback: Callable | None = None,
) -> "BaseAgent":
    """Create PhoneAgent instance."""
    from phone_agent import PhoneAgent

    return PhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
        takeover_callback=takeover_callback,
        confirmation_callback=confirmation_callback,
    )


def _create_mai_agent(
    model_config: "ModelConfig",
    agent_config: "AgentConfig",
    agent_specific_config: dict[str, Any],
    takeover_callback: Callable | None = None,
    confirmation_callback: Callable | None = None,
) -> "BaseAgent":
    """Create MAI Agent adapter instance."""
    from .mai_adapter import MAIAgentAdapter, MAIAgentConfig

    # Build MAI config from dict
    mai_config = MAIAgentConfig(
        history_n=agent_specific_config.get("history_n", 3),
        max_pixels=agent_specific_config.get("max_pixels"),
        min_pixels=agent_specific_config.get("min_pixels"),
        tools=agent_specific_config.get("tools"),
        use_mai_prompt=agent_specific_config.get("use_mai_prompt", False),
    )

    return MAIAgentAdapter(
        model_config=model_config,
        agent_config=agent_config,
        mai_config=mai_config,
        takeover_callback=takeover_callback,
        confirmation_callback=confirmation_callback,
    )


# Register built-in agents
register_agent("glm", _create_phone_agent)
register_agent("mai", _create_mai_agent)
