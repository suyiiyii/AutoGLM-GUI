"""Conversation history manager with JSON file persistence."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.models.history import ConversationRecord, DeviceHistory

# ADB serialno 合法字符：字母数字、下划线、破折号、冒号、点
# USB: ABC123DEF456
# WiFi: 192.168.1.100:5555
# mDNS: adb-243a09b7._adb-tls-connect._tcp
_SERIALNO_PATTERN = re.compile(r"^[a-zA-Z0-9_\-:\.]+$")


class HistoryManager:
    """对话历史管理器（单例模式）."""

    _instance: Optional["HistoryManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._history_dir = Path.home() / ".config" / "autoglm" / "history"
        self._file_cache: dict[str, DeviceHistory] = {}
        self._file_mtime: dict[str, float] = {}

    def _sanitize_serialno(self, serialno: str) -> str:
        """将 serialno 转换为安全的文件名.

        如果 serialno 包含合法字符，直接使用；否则使用 SHA1 哈希作为文件名。
        这样可以防止路径遍历攻击，同时保证功能正常。
        """
        if not serialno:
            return hashlib.sha1(b"empty").hexdigest()

        # 检查是否包含路径遍历字符或不合法字符
        if ".." in serialno or not _SERIALNO_PATTERN.match(serialno):
            # 使用 SHA1 哈希作为安全的文件名
            hashed = hashlib.sha1(serialno.encode("utf-8")).hexdigest()
            logger.warning(
                f"Unsafe serialno detected, using hash: {serialno!r} -> {hashed}"
            )
            return hashed

        return serialno

    def _get_history_path(self, serialno: str) -> Path:
        """获取历史记录文件路径（带路径遍历防护）."""
        safe_name = self._sanitize_serialno(serialno)
        path = (self._history_dir / f"{safe_name}.json").resolve()

        # 防御深度：确保解析后的路径仍在 history_dir 内
        history_dir_resolved = self._history_dir.resolve()
        if not path.is_relative_to(history_dir_resolved):
            # 理论上不应该到这里，但作为最后防线
            hashed = hashlib.sha1(serialno.encode("utf-8")).hexdigest()
            logger.error(f"Path escape detected for {serialno!r}, using hash: {hashed}")
            path = history_dir_resolved / f"{hashed}.json"

        return path

    def _load_history(self, serialno: str) -> DeviceHistory:
        path = self._get_history_path(serialno)

        if not path.exists():
            return DeviceHistory(serialno=serialno)

        current_mtime = path.stat().st_mtime
        if (
            serialno in self._file_mtime
            and self._file_mtime[serialno] == current_mtime
            and serialno in self._file_cache
        ):
            return self._file_cache[serialno]

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            history = DeviceHistory.from_dict(data)
            self._file_cache[serialno] = history
            self._file_mtime[serialno] = current_mtime
            logger.debug(f"Loaded {len(history.records)} records for {serialno}")
            return history
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load history for {serialno}: {e}")
            return DeviceHistory(serialno=serialno)

    def _save_history(self, history: DeviceHistory) -> bool:
        self._history_dir.mkdir(parents=True, exist_ok=True)
        path = self._get_history_path(history.serialno)
        temp_path = path.with_suffix(".tmp")

        try:
            history.last_updated = datetime.now()
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(history.to_dict(), f, indent=2, ensure_ascii=False)
            temp_path.replace(path)

            self._file_cache[history.serialno] = history
            self._file_mtime[history.serialno] = path.stat().st_mtime
            logger.debug(f"Saved {len(history.records)} records for {history.serialno}")
            return True
        except Exception as e:
            logger.error(f"Failed to save history for {history.serialno}: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False

    def add_record(self, serialno: str, record: ConversationRecord) -> None:
        history = self._load_history(serialno)
        history.records.insert(0, record)
        self._save_history(history)
        logger.info(f"Added history record for {serialno}: {record.id}")

    def list_records(
        self, serialno: str, limit: int = 50, offset: int = 0
    ) -> list[ConversationRecord]:
        history = self._load_history(serialno)
        return history.records[offset : offset + limit]

    def get_record(self, serialno: str, record_id: str) -> Optional[ConversationRecord]:
        history = self._load_history(serialno)
        return next((r for r in history.records if r.id == record_id), None)

    def delete_record(self, serialno: str, record_id: str) -> bool:
        history = self._load_history(serialno)
        original_len = len(history.records)
        history.records = [r for r in history.records if r.id != record_id]

        if len(history.records) < original_len:
            self._save_history(history)
            logger.info(f"Deleted history record {record_id} for {serialno}")
            return True

        logger.warning(f"Record {record_id} not found for {serialno}")
        return False

    def clear_device_history(self, serialno: str) -> bool:
        path = self._get_history_path(serialno)
        if path.exists():
            path.unlink()
            self._file_cache.pop(serialno, None)
            self._file_mtime.pop(serialno, None)
            logger.info(f"Cleared all history for {serialno}")
            return True
        return False

    def get_total_count(self, serialno: str) -> int:
        history = self._load_history(serialno)
        return len(history.records)


history_manager = HistoryManager()
