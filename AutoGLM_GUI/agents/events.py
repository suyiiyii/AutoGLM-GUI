from enum import Enum
from typing import Any, TypedDict


class AgentEventType(str, Enum):
    """Agent 事件类型."""

    THINKING = "thinking_chunk"
    STEP = "step"
    DONE = "done"
    ERROR = "error"
    ABORTED = "aborted"


class AgentEvent(TypedDict):
    """Agent 事件（统一类型）."""

    type: str  # 使用字符串以兼容现有 SSE 类型
    data: dict[str, Any]
