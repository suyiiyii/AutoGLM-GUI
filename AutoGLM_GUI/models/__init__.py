"""Data models for AutoGLM-GUI."""

from AutoGLM_GUI.models.device_group import (
    DEFAULT_GROUP_ID,
    DEFAULT_GROUP_NAME,
    DeviceGroup,
)
from AutoGLM_GUI.models.history import ConversationRecord, DeviceHistory
from AutoGLM_GUI.models.scheduled_task import ScheduledTask

__all__ = [
    "ConversationRecord",
    "DeviceHistory",
    "DeviceGroup",
    "DEFAULT_GROUP_ID",
    "DEFAULT_GROUP_NAME",
    "ScheduledTask",
]
