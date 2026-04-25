"""Persistent storage for registered remote device agents."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from AutoGLM_GUI.logger import logger


class RemoteDeviceRegistryManager:
    """Persist remote device registrations across server restarts."""

    _instance: RemoteDeviceRegistryManager | None = None
    _lock = threading.Lock()

    def __init__(self, storage_dir: Path | None = None):
        if storage_dir is None:
            storage_dir = Path.home() / ".config" / "autoglm" / "devices"

        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.storage_dir / "remote_devices.json"
        self._data_lock = threading.RLock()
        self._configs: dict[str, dict[str, str]] = {}
        self._load()

    @classmethod
    def get_instance(
        cls, storage_dir: Path | None = None
    ) -> RemoteDeviceRegistryManager:
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(storage_dir=storage_dir)
                    logger.info("RemoteDeviceRegistryManager singleton created")
        return cls._instance

    def _load(self) -> None:
        if not self.registry_file.exists():
            logger.debug("No remote device registry file found, starting fresh")
            return

        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("registry payload must be an object")
            self._configs = {
                serial: {
                    "base_url": str(config["base_url"]).rstrip("/"),
                    "device_id": str(config["device_id"]),
                }
                for serial, config in data.items()
                if isinstance(config, dict)
                and config.get("base_url")
                and config.get("device_id")
            }
            logger.info(
                "Loaded %d persisted remote device registration(s)",
                len(self._configs),
            )
        except Exception as exc:
            logger.error("Failed to load remote device registry: %s", exc)
            backup_path = self.registry_file.with_suffix(".json.bak")
            try:
                self.registry_file.replace(backup_path)
                logger.warning(
                    "Corrupted remote device registry moved to %s", backup_path.name
                )
            except Exception as backup_exc:
                logger.error(
                    "Failed to backup remote device registry after load error: %s",
                    backup_exc,
                )
            self._configs = {}

    def _save(self) -> None:
        temp_path = self.registry_file.with_suffix(".json.tmp")
        try:
            with self._data_lock:
                payload = dict(self._configs)
            temp_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            temp_path.replace(self.registry_file)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def list_configs(self) -> dict[str, dict[str, str]]:
        with self._data_lock:
            return {serial: dict(config) for serial, config in self._configs.items()}

    def set_config(self, serial: str, *, base_url: str, device_id: str) -> None:
        with self._data_lock:
            self._configs[serial] = {
                "base_url": base_url.rstrip("/"),
                "device_id": device_id,
            }
            self._save()

    def remove_config(self, serial: str) -> None:
        with self._data_lock:
            if self._configs.pop(serial, None) is None:
                return
            self._save()
