"""Scheduled task data models."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


def _normalize_device_serialnos(serialnos: object) -> list[str]:
    if isinstance(serialnos, str):
        serialnos = [serialnos]
    if not isinstance(serialnos, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in serialnos:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s or s in seen:
            continue
        normalized.append(s)
        seen.add(s)
    return normalized


@dataclass
class ScheduledTask:
    """定时任务定义."""

    id: str = field(default_factory=lambda: str(uuid4()))

    # 基础信息
    name: str = ""  # 任务名称
    workflow_uuid: str = ""  # 关联的 Workflow UUID
    device_serialnos: list[str] = field(
        default_factory=list
    )  # 绑定的设备 serialno 列表
    device_group_id: str | None = (
        None  # 绑定的设备分组 ID（与 device_serialnos 二选一）
    )

    # 调度配置
    cron_expression: str = ""  # Cron 表达式 (如 "0 8 * * *")
    enabled: bool = True  # 是否启用

    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 最近执行信息（只记录最后一次）
    last_run_time: datetime | None = None
    last_run_success: bool | None = None
    # success: 全部设备成功；partial: 部分成功；failure: 全部失败
    last_run_status: str | None = None
    last_run_success_count: int | None = None
    last_run_total_count: int | None = None
    last_run_message: str | None = None

    def to_dict(self) -> dict:
        """转换为可序列化的字典."""
        return {
            "id": self.id,
            "name": self.name,
            "workflow_uuid": self.workflow_uuid,
            "device_serialnos": self.device_serialnos,
            "device_group_id": self.device_group_id,
            "cron_expression": self.cron_expression,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_run_time": self.last_run_time.isoformat()
            if self.last_run_time
            else None,
            "last_run_success": self.last_run_success,
            "last_run_status": self.last_run_status,
            "last_run_success_count": self.last_run_success_count,
            "last_run_total_count": self.last_run_total_count,
            "last_run_message": self.last_run_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        """从字典创建实例，向后兼容旧数据格式."""
        # 处理设备序列号：支持旧格式的单字符串和新格式的列表
        device_serialnos = _normalize_device_serialnos(data.get("device_serialnos", []))
        if not device_serialnos:
            # 向后兼容：尝试读取旧字段 device_serialno
            old_device = _normalize_device_serialnos(data.get("device_serialno", ""))
            device_serialnos = old_device

        return cls(
            id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            workflow_uuid=data.get("workflow_uuid", ""),
            device_serialnos=device_serialnos,
            device_group_id=data.get("device_group_id"),
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
            last_run_status=data.get("last_run_status"),
            last_run_success_count=data.get("last_run_success_count"),
            last_run_total_count=data.get("last_run_total_count"),
            last_run_message=data.get("last_run_message"),
        )
