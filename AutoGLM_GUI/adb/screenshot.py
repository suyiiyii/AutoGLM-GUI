"""Screenshot utilities for capturing Android device screen.

DEPRECATED: This module now delegates to adb_plus.screenshot for the actual implementation.
Use adb_plus.screenshot directly for new code.
"""

from AutoGLM_GUI.adb_plus.screenshot import Screenshot, capture_screenshot


def get_screenshot(device_id: str | None = None, timeout: int = 10) -> Screenshot:
    return capture_screenshot(device_id=device_id, timeout=timeout)
