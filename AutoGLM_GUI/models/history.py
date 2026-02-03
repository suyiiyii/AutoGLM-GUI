"""Conversation history data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

# Type alias for serializable dict
SerializableDict = dict[str, Any]


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

    def to_dict(self) -> SerializableDict:
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
    def from_dict(cls, data: SerializableDict) -> "MessageRecord":
        """从字典创建实例."""
        role_value = data.get("role", "user")
        # Ensure role is a valid literal
        role: Literal["user", "assistant"] = (
            "assistant" if role_value == "assistant" else "user"
        )
        timestamp_str = data.get("timestamp")
        return cls(
            role=role,
            content=str(data.get("content", "")),
            timestamp=datetime.fromisoformat(str(timestamp_str))
            if timestamp_str
            else datetime.now(),
            thinking=data.get("thinking"),  # type: ignore[arg-type]
            action=data.get("action"),  # type: ignore[arg-type]
            step=data.get("step"),  # type: ignore[arg-type]
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

    # 完整对话消息列表
    messages: list[MessageRecord] = field(default_factory=list)

    def to_dict(self) -> SerializableDict:
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
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: SerializableDict) -> "ConversationRecord":
        """从字典创建实例."""
        source_value = data.get("source", "chat")
        # Ensure source is a valid literal
        source: Literal["chat", "layered", "scheduled"] = (
            "layered"
            if source_value == "layered"
            else "scheduled"
            if source_value == "scheduled"
            else "chat"
        )
        start_time_str = data.get("start_time")
        end_time_str = data.get("end_time")
        messages_data = data.get("messages", [])
        return cls(
            id=str(data.get("id", str(uuid4()))),
            task_text=str(data.get("task_text", "")),
            final_message=str(data.get("final_message", "")),
            success=bool(data.get("success", False)),
            steps=int(data.get("steps", 0)),
            start_time=datetime.fromisoformat(str(start_time_str))
            if start_time_str
            else datetime.now(),
            end_time=datetime.fromisoformat(str(end_time_str))
            if end_time_str
            else None,
            duration_ms=int(data.get("duration_ms", 0)),
            source=source,
            source_detail=str(data.get("source_detail", "")),
            error_message=data.get("error_message"),  # type: ignore[arg-type]
            messages=[
                MessageRecord.from_dict(m)
                for m in (messages_data if isinstance(messages_data, list) else [])
            ],
        )


@dataclass
class DeviceHistory:
    """设备对话历史（一个设备一个文件）."""

    serialno: str
    records: list[ConversationRecord] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> SerializableDict:
        """转换为可序列化的字典."""
        return {
            "serialno": self.serialno,
            "records": [r.to_dict() for r in self.records],
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: SerializableDict) -> "DeviceHistory":
        """从字典创建实例."""
        last_updated_str = data.get("last_updated")
        records_data = data.get("records", [])
        return cls(
            serialno=str(data.get("serialno", "")),
            records=[
                ConversationRecord.from_dict(r)
                for r in (records_data if isinstance(records_data, list) else [])
            ],
            last_updated=datetime.fromisoformat(str(last_updated_str))
            if last_updated_str
            else datetime.now(),
        )
