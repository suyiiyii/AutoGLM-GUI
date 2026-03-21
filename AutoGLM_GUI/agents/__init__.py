from __future__ import annotations

from typing import Any
from collections.abc import Callable

from .protocols import AsyncAgent


def register_agent(agent_type: str, creator: Callable[..., Any]) -> None:
    from .factory import register_agent as _register_agent

    _register_agent(agent_type=agent_type, creator=creator)


def create_agent(
    agent_type: str,
    model_config: Any,
    agent_config: Any,
    agent_specific_config: Any,
    device: Any,
    takeover_callback: Callable[..., Any] | None = None,
    confirmation_callback: Callable[..., Any] | None = None,
) -> AsyncAgent:
    from .factory import create_agent as _create_agent

    return _create_agent(
        agent_type=agent_type,
        model_config=model_config,
        agent_config=agent_config,
        agent_specific_config=agent_specific_config,
        device=device,
        takeover_callback=takeover_callback,
        confirmation_callback=confirmation_callback,
    )


def list_agent_types() -> list[str]:
    from .factory import list_agent_types as _list_agent_types

    return _list_agent_types()


def is_agent_type_registered(agent_type: str) -> bool:
    from .factory import is_agent_type_registered as _is_agent_type_registered

    return _is_agent_type_registered(agent_type)


__all__ = [
    "AsyncAgent",
    "create_agent",
    "is_agent_type_registered",
    "list_agent_types",
    "register_agent",
]
