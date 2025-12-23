"""Touch control utilities using ADB motion events for real-time dragging."""

import subprocess
import time


def _get_adb_prefix(device_id: str | None, adb_path: str = "adb") -> list[str]:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return [adb_path, "-s", device_id]
    return [adb_path]


def touch_down(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float = 0.0,
    adb_path: str = "adb",
) -> None:
    """
    Send touch DOWN event at specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after event (default: 0.0 for real-time).
        adb_path: Path to adb binary.
    """
    adb_prefix = _get_adb_prefix(device_id, adb_path)

    subprocess.run(
        adb_prefix + ["shell", "input", "motionevent", "DOWN", str(x), str(y)],
        capture_output=True,
    )
    if delay > 0:
        time.sleep(delay)


def touch_move(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float = 0.0,
    adb_path: str = "adb",
) -> None:
    """
    Send touch MOVE event at specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after event (default: 0.0 for real-time).
        adb_path: Path to adb binary.
    """
    adb_prefix = _get_adb_prefix(device_id, adb_path)

    subprocess.run(
        adb_prefix + ["shell", "input", "motionevent", "MOVE", str(x), str(y)],
        capture_output=True,
    )
    if delay > 0:
        time.sleep(delay)


def touch_up(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float = 0.0,
    adb_path: str = "adb",
) -> None:
    """
    Send touch UP event at specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after event (default: 0.0 for real-time).
        adb_path: Path to adb binary.
    """
    adb_prefix = _get_adb_prefix(device_id, adb_path)

    subprocess.run(
        adb_prefix + ["shell", "input", "motionevent", "UP", str(x), str(y)],
        capture_output=True,
    )
    if delay > 0:
        time.sleep(delay)
