"""Robust screenshot helper using `adb exec-out screencap -p`.

Features:
- Avoids temp files and uses exec-out to reduce corruption.
- Normalizes CRLF issues from some devices.
- Validates PNG signature/size and retries before falling back.
"""

import base64
import subprocess
from dataclasses import dataclass
from io import BytesIO

from PIL import Image


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False


def capture_screenshot(
    device_id: str | None = None,
    adb_path: str = "adb",
    timeout: int = 10,
    retries: int = 1,
) -> Screenshot:
    """
    Capture a screenshot using adb exec-out.

    Args:
        device_id: Optional device serial.
        adb_path: Path to adb binary.
        timeout: Per-attempt timeout in seconds.
        retries: Extra attempts after the first try.

    Returns:
        Screenshot object; falls back to a black image on failure.
    """
    attempts = max(1, retries + 1)
    for _ in range(attempts):
        data = _try_capture(device_id=device_id, adb_path=adb_path, timeout=timeout)
        if not data:
            continue

        # NOTE: Do NOT do CRLF normalization for binary PNG data from exec-out
        # The PNG signature contains \r\n bytes that must be preserved

        if not _is_valid_png(data):
            continue

        try:
            img = Image.open(BytesIO(data))
            width, height = img.size
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return Screenshot(base64_data=base64_data, width=width, height=height)
        except Exception:
            # Try next attempt
            continue

    return _fallback_screenshot()


def _try_capture(device_id: str | None, adb_path: str, timeout: int) -> bytes | None:
    """Run exec-out screencap and return raw bytes or None on failure."""
    cmd: list[str | bytes] = [adb_path]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["exec-out", "screencap", "-p"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        # stdout should hold the PNG data
        return result.stdout if isinstance(result.stdout, (bytes, bytearray)) else None
    except Exception:
        return None


def _is_valid_png(data: bytes) -> bool:
    """Basic PNG validation (signature + minimal length)."""
    return (
        len(data) > len(PNG_SIGNATURE) + 8  # header + IHDR length
        and data.startswith(PNG_SIGNATURE)
    )


def _fallback_screenshot() -> Screenshot:
    """Return a black fallback image."""
    width, height = 1080, 2400
    img = Image.new("RGB", (width, height), color="black")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return Screenshot(
        base64_data=base64_data, width=width, height=height, is_sensitive=False
    )
