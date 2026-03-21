"""Type definitions for actions."""

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


@dataclass
class ActionResult:
    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False


class Action(TypedDict, total=False):
    """Base action type with common fields."""

    action: str
    _metadata: dict[str, Any] | None
    # Element-based actions (tap, double_tap, long_press)
    element: list[int] | None
    # Launch action
    app: str | None
    # Type action
    text: str | None
    # Swipe action
    start: list[int] | None
    end: list[int] | None
    # Wait action
    duration: str | None
    # Takeover action
    message: str | None


# Type alias for backward compatibility
ActionType = Action
