"""Custom exceptions for AutoGLM-GUI."""


class InterruptedError(Exception):
    """Raised when a task is interrupted by the user."""

    def __init__(self, message: str = "Task interrupted by user"):
        self.message = message
        super().__init__(self.message)
