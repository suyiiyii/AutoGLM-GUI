"""Device metadata persistence manager."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from AutoGLM_GUI.logger import logger

DISPLAY_NAME_MAX_LENGTH = 100


@dataclass
class DeviceMetadata:
    """Device user-defined metadata."""

    serial: str
    display_name: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        return {
            "serial": self.serial,
            "display_name": self.display_name,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceMetadata":
        """Create instance from dict."""
        last_updated_str = data.get("last_updated")
        last_updated = (
            datetime.fromisoformat(last_updated_str)
            if last_updated_str
            else datetime.now()
        )
        return cls(
            serial=data.get("serial", ""),
            display_name=data.get("display_name"),
            last_updated=last_updated,
        )


class DeviceMetadataManager:
    """
    Singleton manager for device metadata persistence.

    Stores user-defined device names and other metadata.
    Design: Lazy persistence - only save when metadata changes.
    """

    _instance: Optional[DeviceMetadataManager] = None
    _lock = threading.Lock()

    def __init__(self, storage_dir: Optional[Path] = None):
        """Private constructor. Use get_instance() instead."""
        if storage_dir is None:
            storage_dir = Path.home() / ".config" / "autoglm" / "devices"

        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.storage_dir / "metadata.json"

        self._metadata: dict[str, DeviceMetadata] = {}
        self._data_lock = threading.RLock()

        self._load_metadata()

    @classmethod
    def get_instance(cls, storage_dir: Optional[Path] = None) -> DeviceMetadataManager:
        """Get singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(storage_dir=storage_dir)
                    logger.info("DeviceMetadataManager singleton created")
        return cls._instance

    def _load_metadata(self) -> None:
        """Load metadata from disk."""
        if not self.metadata_file.exists():
            logger.debug("No metadata file found, starting fresh")
            return

        try:
            with open(self.metadata_file, encoding="utf-8") as f:
                data = json.load(f)

            with self._data_lock:
                self._metadata = {
                    serial: DeviceMetadata.from_dict(meta_dict)
                    for serial, meta_dict in data.items()
                }

            logger.info(f"Loaded metadata for {len(self._metadata)} device(s)")
        except Exception as e:
            logger.error(f"Failed to load device metadata: {e}")
            backup_path = self.metadata_file.with_suffix(".json.bak")
            if self.metadata_file.exists():
                try:
                    self.metadata_file.rename(backup_path)
                    logger.warning(
                        f"Corrupted metadata file moved to {backup_path.name}"
                    )
                except Exception as backup_error:
                    logger.error(f"Failed to create backup: {backup_error}")
            self._metadata = {}

    def _save_metadata(self) -> None:
        """Save metadata to disk atomically."""
        temp_path = self.metadata_file.with_suffix(".json.tmp")
        try:
            with self._data_lock:
                data = {
                    serial: meta.to_dict() for serial, meta in self._metadata.items()
                }

            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            temp_path.replace(self.metadata_file)

            logger.debug(f"Saved metadata for {len(self._metadata)} device(s)")
        except Exception as e:
            logger.error(f"Failed to save device metadata: {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise

    def get_display_name(self, serial: str) -> Optional[str]:
        """Get device display name by serial."""
        with self._data_lock:
            metadata = self._metadata.get(serial)
            return metadata.display_name if metadata else None

    def set_display_name(self, serial: str, display_name: Optional[str]) -> None:
        """Set device display name. Empty string will be treated as None."""
        normalized_name = display_name.strip() if display_name else None
        normalized_name = normalized_name if normalized_name else None

        if normalized_name and len(normalized_name) > DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(
                f"Display name too long: {len(normalized_name)} > {DISPLAY_NAME_MAX_LENGTH}"
            )

        with self._data_lock:
            if serial not in self._metadata:
                self._metadata[serial] = DeviceMetadata(serial=serial)

            current_name = self._metadata[serial].display_name
            if current_name == normalized_name:
                return

            self._metadata[serial].display_name = normalized_name
            self._metadata[serial].last_updated = datetime.now()

            self._save_metadata()

        logger.info(f"Updated display name for device {serial}: {normalized_name}")

    def get_metadata(self, serial: str) -> Optional[DeviceMetadata]:
        """Get full device metadata."""
        with self._data_lock:
            return self._metadata.get(serial)

    def list_all_metadata(self) -> dict[str, DeviceMetadata]:
        """List all stored device metadata."""
        with self._data_lock:
            return dict(self._metadata)
