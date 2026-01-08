"""Scheduled task data models."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass
class ScheduledTask:
    """定时任务定义."""

    id: str = field(default_factory=lambda: str(uuid4()))

    # 基础信息
    name: str = ""  # 任务名称
    workflow_uuid: str = ""  # 关联的 Workflow UUID
    device_serialno: str = ""  # 绑定的设备 serialno

    # 调度配置
    cron_expression: str = ""  # Cron 表达式 (如 "0 8 * * *")
    enabled: bool = True  # 是否启用

    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 最近执行信息（只记录最后一次）
    last_run_time: datetime | None = None
    last_run_success: bool | None = None
    last_run_message: str | None = None

    def to_dict(self) -> dict:
        """转换为可序列化的字典."""
        return {
            "id": self.id,
            "name": self.name,
            "workflow_uuid": self.workflow_uuid,
            "device_serialno": self.device_serialno,
            "cron_expression": self.cron_expression,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_run_time": self.last_run_time.isoformat()
            if self.last_run_time
            else None,
            "last_run_success": self.last_run_success,
            "last_run_message": self.last_run_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        """从字典创建实例."""
        return cls(
            id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            workflow_uuid=data.get("workflow_uuid", ""),
            device_serialno=data.get("device_serialno", ""),
            cron_expression=data.get("cron_expression", ""),
            enabled=data.get("enabled", True),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.now(),
            last_run_time=datetime.fromisoformat(data["last_run_time"])
            if data.get("last_run_time")
            else None,
            last_run_success=data.get("last_run_success"),
            last_run_message=data.get("last_run_message"),
        )
