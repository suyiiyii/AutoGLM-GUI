"""Type definitions for actions."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ActionResult:
    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False


Action = dict[str, Any]
