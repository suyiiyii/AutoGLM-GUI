"""Conversation history data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


@dataclass
class MessageRecord:
    """对话中的单条消息记录."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    # assistant 消息特有字段
    thinking: str | None = None
    action: dict[str, Any] | None = None
    step: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "thinking": self.thinking,
            "action": self.action,
            "step": self.step,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageRecord:
        """从字典创建实例."""
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if data.get("timestamp")
            else datetime.now(tz=timezone.utc),
            thinking=data.get("thinking"),
            action=data.get("action"),
            step=data.get("step"),
        )


@dataclass
class StepTimingRecord:
    """Step-level timing summary derived from trace spans."""

    step: int
    trace_id: str
    total_duration_ms: float = 0.0
    screenshot_duration_ms: float = 0.0
    current_app_duration_ms: float = 0.0
    llm_duration_ms: float = 0.0
    parse_action_duration_ms: float = 0.0
    execute_action_duration_ms: float = 0.0
    update_context_duration_ms: float = 0.0
    adb_duration_ms: float = 0.0
    sleep_duration_ms: float = 0.0
    other_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "step": self.step,
            "trace_id": self.trace_id,
            "total_duration_ms": self.total_duration_ms,
            "screenshot_duration_ms": self.screenshot_duration_ms,
            "current_app_duration_ms": self.current_app_duration_ms,
            "llm_duration_ms": self.llm_duration_ms,
            "parse_action_duration_ms": self.parse_action_duration_ms,
            "execute_action_duration_ms": self.execute_action_duration_ms,
            "update_context_duration_ms": self.update_context_duration_ms,
            "adb_duration_ms": self.adb_duration_ms,
            "sleep_duration_ms": self.sleep_duration_ms,
            "other_duration_ms": self.other_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepTimingRecord:
        """Create an instance from a dictionary."""
        return cls(
            step=int(data.get("step", 0)),
            trace_id=str(data.get("trace_id", "")),
            total_duration_ms=float(data.get("total_duration_ms", 0.0)),
            screenshot_duration_ms=float(data.get("screenshot_duration_ms", 0.0)),
            current_app_duration_ms=float(data.get("current_app_duration_ms", 0.0)),
            llm_duration_ms=float(data.get("llm_duration_ms", 0.0)),
            parse_action_duration_ms=float(data.get("parse_action_duration_ms", 0.0)),
            execute_action_duration_ms=float(
                data.get("execute_action_duration_ms", 0.0)
            ),
            update_context_duration_ms=float(
                data.get("update_context_duration_ms", 0.0)
            ),
            adb_duration_ms=float(data.get("adb_duration_ms", 0.0)),
            sleep_duration_ms=float(data.get("sleep_duration_ms", 0.0)),
            other_duration_ms=float(data.get("other_duration_ms", 0.0)),
        )


@dataclass
class TraceSummaryRecord:
    """Task-level timing summary derived from trace spans."""

    trace_id: str
    steps: int = 0
    total_duration_ms: float = 0.0
    screenshot_duration_ms: float = 0.0
    current_app_duration_ms: float = 0.0
    llm_duration_ms: float = 0.0
    parse_action_duration_ms: float = 0.0
    execute_action_duration_ms: float = 0.0
    update_context_duration_ms: float = 0.0
    adb_duration_ms: float = 0.0
    sleep_duration_ms: float = 0.0
    other_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "trace_id": self.trace_id,
            "steps": self.steps,
            "total_duration_ms": self.total_duration_ms,
            "screenshot_duration_ms": self.screenshot_duration_ms,
            "current_app_duration_ms": self.current_app_duration_ms,
            "llm_duration_ms": self.llm_duration_ms,
            "parse_action_duration_ms": self.parse_action_duration_ms,
            "execute_action_duration_ms": self.execute_action_duration_ms,
            "update_context_duration_ms": self.update_context_duration_ms,
            "adb_duration_ms": self.adb_duration_ms,
            "sleep_duration_ms": self.sleep_duration_ms,
            "other_duration_ms": self.other_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceSummaryRecord:
        """Create an instance from a dictionary."""
        return cls(
            trace_id=str(data.get("trace_id", "")),
            steps=int(data.get("steps", 0)),
            total_duration_ms=float(data.get("total_duration_ms", 0.0)),
            screenshot_duration_ms=float(data.get("screenshot_duration_ms", 0.0)),
            current_app_duration_ms=float(data.get("current_app_duration_ms", 0.0)),
            llm_duration_ms=float(data.get("llm_duration_ms", 0.0)),
            parse_action_duration_ms=float(data.get("parse_action_duration_ms", 0.0)),
            execute_action_duration_ms=float(
                data.get("execute_action_duration_ms", 0.0)
            ),
            update_context_duration_ms=float(
                data.get("update_context_duration_ms", 0.0)
            ),
            adb_duration_ms=float(data.get("adb_duration_ms", 0.0)),
            sleep_duration_ms=float(data.get("sleep_duration_ms", 0.0)),
            other_duration_ms=float(data.get("other_duration_ms", 0.0)),
        )


@dataclass
class ConversationRecord:
    """单条对话记录."""

    id: str = field(default_factory=lambda: str(uuid4()))

    # 任务信息
    task_text: str = ""  # 用户输入的任务
    final_message: str = ""  # 最终结果消息

    # 执行信息
    success: bool = False
    steps: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration_ms: int = 0  # 执行时长（毫秒）

    # 来源标记
    source: Literal["chat", "layered", "scheduled"] = "chat"
    source_detail: str = ""  # 定时任务名称 or session_id

    # 错误信息
    error_message: str | None = None

    # Trace 信息
    trace_id: str | None = None
    step_timings: list[StepTimingRecord] = field(default_factory=list)
    trace_summary: TraceSummaryRecord | None = None

    # 完整对话消息列表
    messages: list[MessageRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典."""
        return {
            "id": self.id,
            "task_text": self.task_text,
            "final_message": self.final_message,
            "success": self.success,
            "steps": self.steps,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "source": self.source,
            "source_detail": self.source_detail,
            "error_message": self.error_message,
            "trace_id": self.trace_id,
            "step_timings": [timing.to_dict() for timing in self.step_timings],
            "trace_summary": (
                self.trace_summary.to_dict() if self.trace_summary else None
            ),
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationRecord:
        """从字典创建实例."""
        return cls(
            id=data.get("id", str(uuid4())),
            task_text=data.get("task_text", ""),
            final_message=data.get("final_message", ""),
            success=data.get("success", False),
            steps=data.get("steps", 0),
            start_time=datetime.fromisoformat(data["start_time"])
            if data.get("start_time")
            else datetime.now(tz=timezone.utc),
            end_time=datetime.fromisoformat(data["end_time"])
            if data.get("end_time")
            else None,
            duration_ms=data.get("duration_ms", 0),
            source=data.get("source", "chat"),
            source_detail=data.get("source_detail", ""),
            error_message=data.get("error_message"),
            trace_id=data.get("trace_id"),
            step_timings=[
                StepTimingRecord.from_dict(item)
                for item in data.get("step_timings", [])
            ],
            trace_summary=TraceSummaryRecord.from_dict(data["trace_summary"])
            if data.get("trace_summary")
            else None,
            messages=[MessageRecord.from_dict(m) for m in data.get("messages", [])],
        )


@dataclass
class DeviceHistory:
    """设备对话历史（一个设备一个文件）."""

    serialno: str
    records: list[ConversationRecord] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典."""
        return {
            "serialno": self.serialno,
            "records": [r.to_dict() for r in self.records],
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceHistory:
        """从字典创建实例."""
        return cls(
            serialno=data.get("serialno", ""),
            records=[ConversationRecord.from_dict(r) for r in data.get("records", [])],
            last_updated=datetime.fromisoformat(data["last_updated"])
            if data.get("last_updated")
            else datetime.now(tz=timezone.utc),
        )
