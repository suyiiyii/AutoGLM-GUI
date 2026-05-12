"""Agent factory for creating different agent implementations.

This module provides a factory pattern + registry for creating agents,
making it easy to add new agent types without modifying existing code.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Callable

from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.types import AgentSpecificConfig

from .protocols import AsyncAgent


# Agent registry: agent_type -> (creator_function, config_schema)
AGENT_REGISTRY: dict[str, Callable[..., AsyncAgent]] = {}


def register_agent(
    agent_type: str,
    creator: Callable[..., AsyncAgent],
) -> None:
    """
    Register a new agent type.

    Args:
        agent_type: Unique identifier for the agent type (e.g., "glm-async", "mai")
        creator: Function that creates the agent instance.
                  Signature: (model_config, agent_config, agent_specific_config, callbacks) -> AsyncAgent

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
    device: DeviceProtocol,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    """
    Create an agent instance using the factory pattern.

    Args:
        agent_type: Type of agent to create (e.g., "glm-async", "mai")
        model_config: Model configuration
        agent_config: Agent configuration
        agent_specific_config: Agent-specific configuration (e.g., MAIConfig fields)
        device: DeviceProtocol instance (provided by PhoneAgentManager)
        takeover_callback: Takeover callback
        confirmation_callback: Confirmation callback

    Returns:
        Agent instance implementing AsyncAgent.

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


def _create_async_glm_agent(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,  # noqa: ARG001
    device: DeviceProtocol,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    """Create AsyncGLMAgent instance.

    This is the async implementation that supports:
    - Native streaming with AsyncIterator
    - Immediate cancellation with asyncio.CancelledError
    - No worker threads or queues needed
    """
    from .glm.async_agent import AsyncGLMAgent

    # Note: AsyncGLMAgent implements AsyncAgent Protocol, but pyright cannot verify
    # async generator function compatibility with Protocol. This is a known limitation
    # of Python's type system. The implementation is correct at runtime.
    return AsyncGLMAgent(  # type: ignore[return-value]
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        confirmation_callback=confirmation_callback,
        takeover_callback=takeover_callback,
    )


def _create_async_mai_agent(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,
    device: DeviceProtocol,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    from .mai.async_agent import AsyncMAIAgent

    history_n = agent_specific_config.get("history_n", 3)

    return AsyncMAIAgent(  # type: ignore[return-value]
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        history_n=history_n,
        confirmation_callback=confirmation_callback,
        takeover_callback=takeover_callback,
    )


def _create_async_gemini_agent(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,  # noqa: ARG001
    device: DeviceProtocol,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    """Create AsyncGeminiAgent instance.

    Uses OpenAI-compatible function calling for general vision models
    (Gemini, GPT-4o, Claude, etc.).
    """
    from .gemini.async_agent import AsyncGeminiAgent

    return AsyncGeminiAgent(  # type: ignore[return-value]
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        confirmation_callback=confirmation_callback,
        takeover_callback=takeover_callback,
    )


register_agent("glm-async", _create_async_glm_agent)
register_agent("async-glm", _create_async_glm_agent)  # 别名
register_agent("mai", _create_async_mai_agent)
register_agent("gemini", _create_async_gemini_agent)
register_agent("general-vision", _create_async_gemini_agent)  # 通用别名


def _create_droidrun_agent(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,  # noqa: ARG001
    device: DeviceProtocol,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    """Create DroidRunAgent instance.

    Wraps DroidRun's DroidAgent as an AsyncAgent.
    DroidRun manages its own ADB connection independently.
    Requires DroidRun Portal APK installed on the device.
    """
    from .droidrun.async_agent import DroidRunAgent

    return DroidRunAgent(  # type: ignore[return-value]
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        takeover_callback=takeover_callback,
        confirmation_callback=confirmation_callback,
    )


register_agent("droidrun", _create_droidrun_agent)


def _create_midscene_agent(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,
    device: DeviceProtocol,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    """Create AsyncMidsceneAgent instance.

    Wraps Midscene.js CLI as an AsyncAgent.
    Requires Node.js / npx in PATH and a vision model configured.
    """
    from .midscene.async_agent import AsyncMidsceneAgent

    # Pass model_family through extra_body so the agent can set MIDSCENE_MODEL_FAMILY
    model_family = agent_specific_config.get("model_family", "")
    if model_family and "model_family" not in model_config.extra_body:
        model_config.extra_body["model_family"] = model_family

    return AsyncMidsceneAgent(  # type: ignore[return-value]
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        takeover_callback=takeover_callback,
        confirmation_callback=confirmation_callback,
    )


register_agent("midscene", _create_midscene_agent)


def _create_qwen_agent(
    model_config: ModelConfig,
    agent_config: AgentConfig,
    agent_specific_config: AgentSpecificConfig,  # noqa: ARG001
    device: DeviceProtocol,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    """Create AsyncQwenAgent instance.

    Uses Qwen model inference logic:
    - <answer> tag parsing for action detection
    - AST-based action parser with bracket repair
    - info() action support for user interaction
    - <thought>/<answer> format prompts
    """
    from .qwen.async_agent import AsyncQwenAgent

    return AsyncQwenAgent(  # type: ignore[return-value]
        model_config=model_config,
        agent_config=agent_config,
        device=device,
        confirmation_callback=confirmation_callback,
        takeover_callback=takeover_callback,
    )


register_agent("qwen", _create_qwen_agent)
