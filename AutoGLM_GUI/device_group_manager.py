"""Device group management module.

Features:
- 单例模式
- JSON 文件持久化
- 基于 mtime 的缓存机制
- 原子文件写入
- 默认分组自动创建
"""

import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Optional

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.models.device_group import (
    DEFAULT_GROUP_ID,
    DeviceGroup,
)


class DeviceGroupManager:
    """设备分组管理器（单例模式）."""

    _instance: Optional["DeviceGroupManager"] = None

    def __new__(cls):
        """单例模式：确保只有一个实例."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化管理器."""
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._groups_path = Path.home() / ".config" / "autoglm" / "device_groups.json"
        self._lock = RLock()

        # 缓存
        self._groups_cache: Optional[list[DeviceGroup]] = None
        self._assignments_cache: Optional[dict[str, str]] = None
        self._file_mtime: Optional[float] = None

    def list_groups(self) -> list[DeviceGroup]:
        """获取所有分组（按 order 排序）.

        Returns:
            list[DeviceGroup]: 分组列表
        """
        with self._lock:
            groups, _ = self._load_data()
            return sorted(groups, key=lambda g: g.order)

    def get_group(self, group_id: str) -> DeviceGroup | None:
        """根据 ID 获取单个分组.

        Args:
            group_id: 分组 ID

        Returns:
            DeviceGroup | None: 分组数据，如果不存在则返回 None
        """
        with self._lock:
            groups, _ = self._load_data()
            return next((g for g in groups if g.id == group_id), None)

    def create_group(self, name: str) -> DeviceGroup:
        """创建新分组.

        Args:
            name: 分组名称

        Returns:
            DeviceGroup: 新创建的分组
        """
        with self._lock:
            groups, assignments = self._load_data()

            # 计算新的 order 值（放在最后）
            max_order = max((g.order for g in groups), default=-1)
            new_group = DeviceGroup(
                name=name,
                order=max_order + 1,
            )

            groups.append(new_group)
            self._save_data(groups, assignments)
            logger.info(f"Created device group: {name} (id={new_group.id})")
            return new_group

    def update_group(self, group_id: str, name: str) -> DeviceGroup | None:
        """更新分组名称.

        Args:
            group_id: 分组 ID
            name: 新名称

        Returns:
            DeviceGroup | None: 更新后的分组，如果不存在则返回 None
        """
        with self._lock:
            groups, assignments = self._load_data()
            for group in groups:
                if group.id == group_id:
                    group.name = name
                    group.updated_at = datetime.now()
                    self._save_data(groups, assignments)
                    logger.info(f"Updated device group: {name} (id={group_id})")
                    return group
            logger.warning(f"Device group not found for update: id={group_id}")
            return None

    def delete_group(self, group_id: str) -> bool:
        """删除分组（设备移回默认分组）.

        Args:
            group_id: 分组 ID

        Returns:
            bool: 删除成功返回 True，不存在或为默认分组返回 False
        """
        if group_id == DEFAULT_GROUP_ID:
            logger.warning("Cannot delete default group")
            return False

        with self._lock:
            groups, assignments = self._load_data()
            original_len = len(groups)
            groups = [g for g in groups if g.id != group_id]

            if len(groups) < original_len:
                # 将该分组的设备移到默认分组
                moved_count = 0
                for serial, gid in list(assignments.items()):
                    if gid == group_id:
                        assignments[serial] = DEFAULT_GROUP_ID
                        moved_count += 1

                self._save_data(groups, assignments)
                logger.info(
                    f"Deleted device group: id={group_id}, "
                    f"moved {moved_count} device(s) to default group"
                )
                return True

            logger.warning(f"Device group not found for deletion: id={group_id}")
            return False

    def reorder_groups(self, group_ids: list[str]) -> bool:
        """调整分组顺序.

        Args:
            group_ids: 按新顺序排列的分组 ID 列表

        Returns:
            bool: 调整成功返回 True
        """
        with self._lock:
            groups, assignments = self._load_data()

            # 创建 ID 到 group 的映射
            group_map = {g.id: g for g in groups}

            # 验证所有 ID 都存在
            for gid in group_ids:
                if gid not in group_map:
                    logger.warning(f"Group not found for reorder: id={gid}")
                    return False

            # 更新 order 值
            for order, gid in enumerate(group_ids):
                group_map[gid].order = order
                group_map[gid].updated_at = datetime.now()

            self._save_data(groups, assignments)
            logger.info(f"Reordered {len(group_ids)} groups")
            return True

    def assign_device(self, serial: str, group_id: str) -> bool:
        """分配设备到分组.

        Args:
            serial: 设备 serial
            group_id: 目标分组 ID

        Returns:
            bool: 分配成功返回 True
        """
        with self._lock:
            groups, assignments = self._load_data()

            # 验证分组存在
            if not any(g.id == group_id for g in groups):
                logger.warning(f"Group not found for assignment: id={group_id}")
                return False

            old_group = assignments.get(serial, DEFAULT_GROUP_ID)
            assignments[serial] = group_id
            self._save_data(groups, assignments)

            if old_group != group_id:
                logger.info(
                    f"Assigned device {serial} to group {group_id} (was: {old_group})"
                )
            return True

    def get_device_group(self, serial: str) -> str:
        """获取设备所属分组 ID.

        Args:
            serial: 设备 serial

        Returns:
            str: 分组 ID（未分配则返回默认分组 ID）
        """
        with self._lock:
            _, assignments = self._load_data()
            return assignments.get(serial, DEFAULT_GROUP_ID)

    def get_devices_in_group(self, group_id: str) -> list[str]:
        """获取分组内的设备 serial 列表.

        Args:
            group_id: 分组 ID

        Returns:
            list[str]: 设备 serial 列表
        """
        with self._lock:
            _, assignments = self._load_data()

            # 对于默认分组，包含未显式分配的设备
            if group_id == DEFAULT_GROUP_ID:
                # 注意：这里只返回显式分配到默认分组的设备
                # 如果需要包含所有未分配设备，需要配合 DeviceManager 使用
                return [
                    serial
                    for serial, gid in assignments.items()
                    if gid == DEFAULT_GROUP_ID
                ]

            return [serial for serial, gid in assignments.items() if gid == group_id]

    def get_all_assignments(self) -> dict[str, str]:
        """获取所有设备分配信息.

        Returns:
            dict[str, str]: serial -> group_id 的映射
        """
        with self._lock:
            _, assignments = self._load_data()
            return assignments.copy()

    def _load_data(self) -> tuple[list[DeviceGroup], dict[str, str]]:
        """从文件加载数据（带 mtime 缓存）.

        Returns:
            tuple[list[DeviceGroup], dict[str, str]]: (分组列表, 设备分配映射)
        """
        # 检查文件是否存在
        if not self._groups_path.exists():
            # 创建默认分组
            default_group = DeviceGroup.create_default_group()
            groups = [default_group]
            assignments: dict[str, str] = {}
            self._save_data(groups, assignments)
            return groups, assignments

        # 检查缓存
        current_mtime = self._groups_path.stat().st_mtime
        if (
            self._file_mtime == current_mtime
            and self._groups_cache is not None
            and self._assignments_cache is not None
        ):
            return self._groups_cache.copy(), self._assignments_cache.copy()

        # 重新加载
        try:
            with open(self._groups_path, encoding="utf-8") as f:
                data = json.load(f)

            groups_data = data.get("groups", [])
            groups = [DeviceGroup.from_dict(g) for g in groups_data]
            assignments = data.get("device_assignments", {})

            # 确保默认分组存在
            if not any(g.id == DEFAULT_GROUP_ID for g in groups):
                default_group = DeviceGroup.create_default_group()
                groups.insert(0, default_group)
                self._save_data(groups, assignments)

            self._groups_cache = groups
            self._assignments_cache = assignments
            self._file_mtime = current_mtime
            logger.debug(
                f"Loaded {len(groups)} groups, {len(assignments)} device assignments"
            )
            return groups.copy(), assignments.copy()

        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load device groups: {e}")
            # 返回默认分组
            default_group = DeviceGroup.create_default_group()
            return [default_group], {}

    def _save_data(
        self, groups: list[DeviceGroup], assignments: dict[str, str]
    ) -> bool:
        """原子写入文件.

        Args:
            groups: 分组列表
            assignments: 设备分配映射

        Returns:
            bool: 保存成功返回 True
        """
        self._groups_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "groups": [g.to_dict() for g in groups],
            "device_assignments": assignments,
        }

        # 原子写入：临时文件 + rename
        temp_path = self._groups_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self._groups_path)

            # 更新缓存
            self._groups_cache = groups.copy()
            self._assignments_cache = assignments.copy()
            self._file_mtime = self._groups_path.stat().st_mtime
            logger.debug(
                f"Saved {len(groups)} groups, {len(assignments)} device assignments"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save device groups: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False


# 单例实例
device_group_manager = DeviceGroupManager()
