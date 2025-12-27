"""Custom exceptions for AutoGLM-GUI."""


class TaskInterruptedError(Exception):
    """Raised when a task is interrupted by the user."""

    def __init__(self, message: str = "Task interrupted by user"):
        self.message = message
        super().__init__(self.message)


class DeviceNotAvailableError(Exception):
    """Raised when a requested device is not available."""

    def __init__(self, message: str = "Device not available"):
        self.message = message
        super().__init__(self.message)
