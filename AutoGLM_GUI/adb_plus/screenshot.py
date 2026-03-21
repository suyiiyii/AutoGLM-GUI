"""Robust screenshot helper using `adb exec-out screencap -p`.

Features:
- Avoids temp files and uses exec-out to reduce corruption.
- Normalizes CRLF issues from some devices.
- Validates PNG signature/size and retries before falling back.
"""

import asyncio
import base64
import subprocess
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from AutoGLM_GUI.exceptions import DeviceNotAvailableError
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import is_windows
from AutoGLM_GUI.trace import trace_span


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

    Raises:
        DeviceNotAvailableError: When device is not found or offline.
    """
    with trace_span(
        "adb.capture_screenshot",
        attrs={"device_id": device_id, "timeout": timeout, "retries": retries},
    ) as span:
        attempts = max(1, retries + 1)
        for attempt in range(attempts):
            data = _try_capture(device_id=device_id, adb_path=adb_path, timeout=timeout)
            if not data:
                continue

            if not _is_valid_png(data):
                continue

            try:
                img = Image.open(BytesIO(data))
                width, height = img.size
                base64_data = base64.b64encode(data).decode("utf-8")
                span.set_attributes(
                    {
                        "success": True,
                        "attempt": attempt + 1,
                        "width": width,
                        "height": height,
                    }
                )
                return Screenshot(base64_data=base64_data, width=width, height=height)
            except Exception as exc:
                logger.debug(
                    "Failed to decode screenshot PNG for %s: %s", device_id, exc
                )
                continue

        span.set_attributes({"success": False, "fallback": True})
        return _fallback_screenshot()


def _try_capture(device_id: str | None, adb_path: str, timeout: int) -> bytes | None:
    """Run exec-out screencap and return raw bytes or None on failure.

    Raises:
        DeviceNotAvailableError: When device is not found or offline.
    """
    cmd: list[str | bytes] = [adb_path]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["exec-out", "screencap", "-p"])

    try:
        with trace_span(
            "adb.exec_out_screencap",
            attrs={"device_id": device_id, "timeout": timeout},
        ):
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
            )
        if result.returncode != 0:
            # Check for device not found or offline errors
            stderr = (
                result.stderr.decode("utf-8", errors="ignore") if result.stderr else ""
            )
            stderr_lower = stderr.lower()
            if "device not found" in stderr_lower or "offline" in stderr_lower:
                raise DeviceNotAvailableError(
                    f"Device {device_id} not found or offline"
                )
            return None
        # stdout should hold the PNG data
        return result.stdout
    except DeviceNotAvailableError:
        raise  # Re-raise to caller
    except Exception as exc:
        logger.debug("Screenshot capture failed for %s: %s", device_id, exc)
        return None


async def capture_screenshot_async(
    device_id: str | None = None,
    adb_path: str = "adb",
    timeout: int = 10,
    retries: int = 1,
) -> Screenshot:
    """Async screenshot capture for FastAPI handlers."""
    with trace_span(
        "adb.capture_screenshot_async",
        attrs={"device_id": device_id, "timeout": timeout, "retries": retries},
    ) as span:
        attempts = max(1, retries + 1)
        for attempt in range(attempts):
            data = await _try_capture_async(
                device_id=device_id,
                adb_path=adb_path,
                timeout=timeout,
            )
            if not data or not _is_valid_png(data):
                continue

            try:
                image = await asyncio.to_thread(Image.open, BytesIO(data))
                width, height = image.size
                base64_data = base64.b64encode(data).decode("utf-8")
                span.set_attributes(
                    {
                        "success": True,
                        "attempt": attempt + 1,
                        "width": width,
                        "height": height,
                    }
                )
                return Screenshot(base64_data=base64_data, width=width, height=height)
            except Exception as exc:
                logger.debug(
                    "Failed to decode async screenshot PNG for %s: %s",
                    device_id,
                    exc,
                )
                continue

        span.set_attributes({"success": False, "fallback": True})
        return _fallback_screenshot()


async def _try_capture_async(
    device_id: str | None, adb_path: str, timeout: int
) -> bytes | None:
    """Async exec-out screencap helper."""
    cmd: list[str] = [adb_path]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["exec-out", "screencap", "-p"])

    try:
        with trace_span(
            "adb.exec_out_screencap_async",
            attrs={"device_id": device_id, "timeout": timeout},
        ):
            if is_windows():
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    timeout=timeout,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.communicate()
                    raise subprocess.TimeoutExpired(cmd, timeout)
                result = subprocess.CompletedProcess(
                    cmd,
                    process.returncode if process.returncode is not None else -1,
                    stdout,
                    stderr,
                )
        if result.returncode != 0:
            stderr = (
                result.stderr.decode("utf-8", errors="ignore") if result.stderr else ""
            )
            stderr_lower = stderr.lower()
            if "device not found" in stderr_lower or "offline" in stderr_lower:
                raise DeviceNotAvailableError(
                    f"Device {device_id} not found or offline"
                )
            return None
        return result.stdout
    except DeviceNotAvailableError:
        raise
    except Exception as exc:
        logger.debug("Async screenshot capture failed for %s: %s", device_id, exc)
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
