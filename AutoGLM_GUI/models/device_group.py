"""Device group data models."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

# Default group ID - this group cannot be deleted
DEFAULT_GROUP_ID = "default"
DEFAULT_GROUP_NAME = "默认分组"


@dataclass
class DeviceGroup:
    """设备分组定义."""

    id: str = field(default_factory=lambda: str(uuid4()))

    # 基础信息
    name: str = ""  # 分组名称
    order: int = 0  # 排序顺序（数字越小越靠前）

    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为可序列化的字典."""
        return {
            "id": self.id,
            "name": self.name,
            "order": self.order,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceGroup":
        """从字典创建实例."""
        return cls(
            id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            order=data.get("order", 0),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.now(),
        )

    @classmethod
    def create_default_group(cls) -> "DeviceGroup":
        """创建默认分组."""
        return cls(
            id=DEFAULT_GROUP_ID,
            name=DEFAULT_GROUP_NAME,
            order=0,
        )

    @property
    def is_default(self) -> bool:
        """是否为默认分组."""
        return self.id == DEFAULT_GROUP_ID
