"""ADB version detection and feature support checking."""

import re
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import run_cmd_silently_sync


def get_adb_version(adb_path: str = "adb") -> tuple[int, int, int] | None:
    """
    Get ADB version as (major, minor, patch) tuple.

    Args:
        adb_path: Path to adb executable

    Returns:
        Version tuple or None if failed

    Example:
        >>> get_adb_version()
        (34, 0, 5)  # ADB version 34.0.5
    """
    try:
        result = run_cmd_silently_sync([adb_path, "version"], timeout=3)

        if result.returncode != 0:
            return None

        # Parse "Android Debug Bridge version 1.0.41"
        # Or "Version 34.0.5-11580240"
        match = re.search(r"version (\d+)\.(\d+)\.(\d+)", result.stdout, re.IGNORECASE)
        if match:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)))

        # Legacy format: "Android Debug Bridge version 1.0.XX"
        match = re.search(r"version 1\.0\.(\d+)", result.stdout)
        if match:
            return (1, 0, int(match.group(1)))

        return None

    except Exception as e:
        logger.debug(f"Failed to get ADB version: {e}")
        return None


def supports_mdns_services(adb_path: str = "adb") -> bool:
    """
    Check if ADB supports 'mdns services' command.

    This feature was added in ADB 30.0.0+ (Android 11 SDK Platform Tools).

    Args:
        adb_path: Path to adb executable

    Returns:
        True if supported, False otherwise
    """
    # Quick feature detection: try running the command
    try:
        result = run_cmd_silently_sync([adb_path, "mdns", "services"], timeout=5)

        # If command succeeds or returns "List of discovered mdns services", it's supported
        if result.returncode == 0 or "mdns services" in result.stdout.lower():
            return True

        # Check for "unknown command" error
        stderr_lower = result.stderr.lower()
        if "unknown" in stderr_lower or "not found" in stderr_lower:
            logger.info(
                "ADB does not support 'mdns services' command (requires ADB 30.0.0+)"
            )
            return False

        # If we get here, assume not supported
        return False

    except Exception as e:
        logger.debug(f"Failed to check mDNS support: {e}")
        return False
