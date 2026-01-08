"""Conversation history manager with JSON file persistence."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.models.history import ConversationRecord, DeviceHistory


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

    def _get_history_path(self, serialno: str) -> Path:
        return self._history_dir / f"{serialno}.json"

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
