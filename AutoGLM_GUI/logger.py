"""
Centralized logging configuration using loguru.
"""

import sys
from pathlib import Path
from loguru import logger

# Remove default handler
logger.remove()

# Default configuration - will be overridden by configure_logger()
_configured = False


def configure_logger(
    console_level: str = "INFO",
    log_file: str | None = "logs/autoglm_{time:YYYY-MM-DD}.log",
    log_level: str = "DEBUG",
    rotation: str = "100 MB",
    retention: str = "7 days",
    compression: str = "zip",
) -> None:
    """
    Configure the global logger with console and file handlers.

    Args:
        console_level: Console output level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path (None to disable file logging)
        log_level: File logging level
        rotation: Log rotation policy (e.g., "100 MB", "1 day")
        retention: Log retention policy (e.g., "7 days", "1 week")
        compression: Compression format for rotated logs (e.g., "zip", "gz")
    """
    global _configured

    # Remove existing handlers if reconfiguring
    if _configured:
        logger.remove()

    # Console handler with colors
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=console_level,
        colorize=True,
    )

    # File handler
    if log_file:
        # Create logs directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            rotation=rotation,
            retention=retention,
            compression=compression,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            encoding="utf-8",
        )

        # Separate error log file
        error_file = str(log_path.parent / f"errors_{log_path.name.split('_', 1)[1]}")
        logger.add(
            error_file,
            rotation="50 MB",
            retention="30 days",
            compression=compression,
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            backtrace=True,
            diagnose=True,
            encoding="utf-8",
        )

    _configured = True


# Note: Logger is NOT auto-initialized to allow early configuration
# The first call to configure_logger() will initialize the logger
# If not configured before use, it will use loguru's default behavior (no handlers)

__all__ = ["logger", "configure_logger"]
