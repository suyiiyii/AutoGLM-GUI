"""Workflow 管理模块.

Features:
- 单例模式
- JSON 文件持久化
- 基于 mtime 的缓存机制
- 原子文件写入
- UUID 生成
"""

from __future__ import annotations

import json
import uuid as uuid_lib
from pathlib import Path
from typing import Any, Self

from AutoGLM_GUI.logger import logger


class WorkflowManager:
    """Workflow 管理器（单例模式）."""

    _instance: Self | None = None

    def __new__(cls: type[Self]) -> Self:
        """单例模式：确保只有一个实例."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化管理器."""
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._workflows_path = Path.home() / ".config" / "autoglm" / "workflows.json"
        self._file_cache: list[dict[str, Any]] | None = None
        self._file_mtime: float | None = None

    def list_workflows(self) -> list[dict[str, Any]]:
        """获取所有 workflows.

        Returns:
            list[dict]: Workflow 列表
        """
        return self._load_workflows()

    def get_workflow(self, uuid: str) -> dict[str, Any] | None:
        """根据 UUID 获取单个 workflow.

        Args:
            uuid: Workflow UUID

        Returns:
            dict | None: Workflow 数据，如果不存在则返回 None
        """
        workflows = self._load_workflows()
        return next((wf for wf in workflows if wf["uuid"] == uuid), None)

    def create_workflow(self, name: str, text: str) -> dict[str, Any]:
        """创建新 workflow.

        Args:
            name: Workflow 名称
            text: Workflow 任务内容

        Returns:
            dict: 新创建的 workflow
        """
        workflows = self._load_workflows()
        new_workflow = {
            "uuid": str(uuid_lib.uuid4()),
            "name": name,
            "text": text,
        }
        workflows.append(new_workflow)
        self._save_workflows(workflows)
        logger.info(f"Created workflow: {name} (uuid={new_workflow['uuid']})")
        return new_workflow

    def update_workflow(self, uuid: str, name: str, text: str) -> dict[str, Any] | None:
        """更新 workflow.

        Args:
            uuid: Workflow UUID
            name: 新名称
            text: 新任务内容

        Returns:
            dict | None: 更新后的 workflow，如果不存在则返回 None
        """
        workflows = self._load_workflows()
        for wf in workflows:
            if wf["uuid"] == uuid:
                wf["name"] = name
                wf["text"] = text
                self._save_workflows(workflows)
                logger.info(f"Updated workflow: {name} (uuid={uuid})")
                return wf
        logger.warning(f"Workflow not found for update: uuid={uuid}")
        return None

    def delete_workflow(self, uuid: str) -> bool:
        """删除 workflow.

        Args:
            uuid: Workflow UUID

        Returns:
            bool: 删除成功返回 True，不存在返回 False
        """
        workflows = self._load_workflows()
        original_len = len(workflows)
        workflows = [wf for wf in workflows if wf["uuid"] != uuid]
        if len(workflows) < original_len:
            self._save_workflows(workflows)
            logger.info(f"Deleted workflow: uuid={uuid}")
            return True
        logger.warning(f"Workflow not found for deletion: uuid={uuid}")
        return False

    def _load_workflows(self) -> list[dict[str, Any]]:
        """从文件加载（带 mtime 缓存）.

        Returns:
            list[dict]: Workflow 列表
        """
        if not self._workflows_path.exists():
            return []

        # 检查缓存
        current_mtime = self._workflows_path.stat().st_mtime
        if self._file_mtime == current_mtime and self._file_cache is not None:
            return self._file_cache.copy()

        # 重新加载
        try:
            with open(self._workflows_path, encoding="utf-8") as f:
                data = json.load(f)
            workflows = data.get("workflows", [])
            self._file_cache = workflows
            self._file_mtime = current_mtime
            logger.debug(f"Loaded {len(workflows)} workflows from file")
            return workflows.copy()
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load workflows: {e}")
            return []

    def _save_workflows(self, workflows: list[dict[str, Any]]) -> bool:
        """原子写入文件.

        Args:
            workflows: Workflow 列表

        Returns:
            bool: 保存成功返回 True
        """
        self._workflows_path.parent.mkdir(parents=True, exist_ok=True)

        data = {"workflows": workflows}

        # 原子写入：临时文件 + rename
        temp_path = self._workflows_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self._workflows_path)

            # 更新缓存
            self._file_cache = workflows.copy()
            self._file_mtime = self._workflows_path.stat().st_mtime
            logger.debug(f"Saved {len(workflows)} workflows to file")
            return True
        except Exception as e:
            logger.error(f"Failed to save workflows: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False


# 单例实例
workflow_manager = WorkflowManager()
