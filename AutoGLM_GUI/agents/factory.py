"""Agent factory for creating different agent implementations.

This module provides a factory pattern + registry for creating agents,
making it easy to add new agent types without modifying existing code.
"""

from __future__ import annotations

from typing import Callable, Dict

from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.types import AgentSpecificConfig

from .protocols import BaseAgent


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
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,
    device,
    takeover_callback: Callable | None = None,
    confirmation_callback: Callable | None = None,
) -> BaseAgent:
    """
    Create an agent instance using the factory pattern.

    Args:
        agent_type: Type of agent to create (e.g., "glm", "mai")
        model_config: Model configuration
        agent_config: Agent configuration
        agent_specific_config: Agent-specific configuration (e.g., MAIConfig fields)
        device: DeviceProtocol instance (provided by PhoneAgentManager)
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
            device=device,
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


def _create_glm_agent_v2(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,
    device,
    takeover_callback: Callable | None = None,
    confirmation_callback: Callable | None = None,
) -> BaseAgent:
    from .glm.agent import GLMAgent

    return GLMAgent(
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        confirmation_callback=confirmation_callback,
        takeover_callback=takeover_callback,
    )


def _create_internal_mai_agent(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,
    device,
    takeover_callback: Callable | None = None,
    confirmation_callback: Callable | None = None,
) -> BaseAgent:
    from .mai.agent import InternalMAIAgent

    history_n = agent_specific_config.get("history_n", 3)

    return InternalMAIAgent(
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        history_n=history_n,
        confirmation_callback=confirmation_callback,
        takeover_callback=takeover_callback,
    )


register_agent("glm", _create_glm_agent_v2)
register_agent("mai", _create_internal_mai_agent)
