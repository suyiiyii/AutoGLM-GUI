"""Custom exceptions for AutoGLM-GUI."""


class DeviceNotAvailableError(Exception):
    """Raised when device is not available (disconnected/offline)."""

    pass


class AgentNotInitializedError(Exception):
    """Raised when attempting to access uninitialized agent."""

    pass


class DeviceBusyError(Exception):
    """Raised when device is currently processing a request."""

    pass


class AgentInitializationError(Exception):
    """Raised when agent initialization fails."""

    pass
