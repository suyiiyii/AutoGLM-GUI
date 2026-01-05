from __future__ import annotations

from typing import Callable


def register_agent(agent_type: str, creator: Callable) -> None:
    from .factory import register_agent as _register_agent

    _register_agent(agent_type=agent_type, creator=creator)


def create_agent(
    agent_type: str,
    model_config,
    agent_config,
    agent_specific_config,
    device,
    takeover_callback: Callable | None = None,
    confirmation_callback: Callable | None = None,
):
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
    "create_agent",
    "register_agent",
    "list_agent_types",
    "is_agent_type_registered",
]
