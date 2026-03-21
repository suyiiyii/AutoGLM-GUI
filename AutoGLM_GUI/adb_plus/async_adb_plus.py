"""Async versions of adb_plus utilities.

This module provides async implementations of all adb_plus functions:
- capture_screenshot
- touch_down, touch_move, touch_up
- get_wifi_ip
- get_device_serial
- pair_device

The sync versions remain in their original modules for backward compatibility.
"""

from __future__ import annotations

import asyncio
import base64
import re
import subprocess
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

from AutoGLM_GUI.exceptions import DeviceNotAvailableError
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import (
    build_adb_command,
    run_adb_async,
    run_cmd_silently,
)
from AutoGLM_GUI.trace import trace_span

if TYPE_CHECKING:
    from PIL import Image

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False


# ==================== Screenshot ====================


async def capture_screenshot(
    device_id: str | None = None,
    adb_path: str = "adb",
    timeout: int = 10,
    retries: int = 1,
) -> Screenshot:
    """
    Capture a screenshot using adb exec-out (async version).

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
        "adb.capture_screenshot_async",
        attrs={"device_id": device_id, "timeout": timeout, "retries": retries},
    ) as span:
        attempts = max(1, retries + 1)
        for attempt in range(attempts):
            data = await _try_capture(device_id=device_id, adb_path=adb_path, timeout=timeout)
            if not data:
                continue

            if not _is_valid_png(data):
                continue

            try:
                from PIL import Image

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
            except Exception:
                continue

        span.set_attributes({"success": False, "fallback": True})
        return _fallback_screenshot()


async def _try_capture(device_id: str | None, adb_path: str, timeout: int) -> bytes | None:
    """Run exec-out screencap and return raw bytes or None on failure (async version).

    Raises:
        DeviceNotAvailableError: When device is not found or offline.
    """
    cmd: list[str] = [adb_path]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(["exec-out", "screencap", "-p"])

    try:
        with trace_span(
            "adb.exec_out_screencap_async",
            attrs={"device_id": device_id, "timeout": timeout},
        ):
            # Use asyncio.to_thread for binary output (run_adb_async returns string)
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                timeout=timeout,
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
    except Exception:
        return None


def _is_valid_png(data: bytes) -> bool:
    """Basic PNG validation (signature + minimal length)."""
    return (
        len(data) > len(PNG_SIGNATURE) + 8
        and data.startswith(PNG_SIGNATURE)
    )


def _fallback_screenshot() -> Screenshot:
    """Return a black fallback image."""
    from PIL import Image

    width, height = 1080, 2400
    img = Image.new("RGB", (width, height), color="black")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return Screenshot(
        base64_data=base64_data, width=width, height=height, is_sensitive=False
    )


# ==================== Touch ====================


async def touch_down(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float = 0.0,
    adb_path: str = "adb",
) -> None:
    """
    Send touch DOWN event at specified coordinates (async version).

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after event (default: 0.0 for real-time).
        adb_path: Path to adb binary.
    """
    adb_prefix = build_adb_command(device_id, adb_path)
    await run_cmd_silently(
        adb_prefix + ["shell", "input", "motionevent", "DOWN", str(x), str(y)]
    )
    if delay > 0:
        await asyncio.sleep(delay)


async def touch_move(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float = 0.0,
    adb_path: str = "adb",
) -> None:
    """
    Send touch MOVE event at specified coordinates (async version).

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after event (default: 0.0 for real-time).
        adb_path: Path to adb binary.
    """
    adb_prefix = build_adb_command(device_id, adb_path)
    await run_cmd_silently(
        adb_prefix + ["shell", "input", "motionevent", "MOVE", str(x), str(y)]
    )
    if delay > 0:
        await asyncio.sleep(delay)


async def touch_up(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float = 0.0,
    adb_path: str = "adb",
) -> None:
    """
    Send touch UP event at specified coordinates (async version).

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after event (default: 0.0 for real-time).
        adb_path: Path to adb binary.
    """
    adb_prefix = build_adb_command(device_id, adb_path)
    await run_cmd_silently(
        adb_prefix + ["shell", "input", "motionevent", "UP", str(x), str(y)]
    )
    if delay > 0:
        await asyncio.sleep(delay)


# ==================== IP ====================


async def _run_async(adb_path: str, device_id: str | None, cmd: list[str]) -> str:
    """Run ADB shell command and return output (async version)."""
    base_cmd = [adb_path]
    if device_id:
        base_cmd.extend(["-s", device_id])
    result = await run_adb_async(base_cmd + ["shell", *cmd], timeout=5)
    return (result.stdout or "") + (result.stderr or "")


def _extract_ip(text: str) -> str | None:
    """Extract IP address from text."""
    m = re.search(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", text)
    if not m:
        return None
    ip = m.group(0)
    if ip == "0.0.0.0":
        return None
    return ip


async def get_wifi_ip(adb_path: str = "adb", device_id: str | None = None) -> str | None:
    """
    Prefer WiFi IP when multiple interfaces exist (async version).

    - First try `ip -4 route get 8.8.8.8`, skip typical cellular interfaces (ccmni/rmnet).
    - Fallback to `ip -4 addr show wlan0`.
    Returns None if no suitable IP is found or on error.
    """
    # 1) route
    try:
        route_out = await _run_async(adb_path, device_id, ["ip", "-4", "route", "get", "8.8.8.8"])
        for line in route_out.splitlines():
            if "src" not in line:
                continue
            parts = line.split()
            iface = None
            ip = None
            if "dev" in parts:
                try:
                    iface = parts[parts.index("dev") + 1]
                except Exception as e:
                    logger.debug(f"Failed to extract 'dev' interface: {e}")
            if "src" in parts:
                try:
                    ip = parts[parts.index("src") + 1]
                except Exception as e:
                    logger.debug(f"Failed to extract 'src' IP: {e}")
            if not ip or ip == "0.0.0.0":
                continue
            if iface and (iface.startswith("ccmni") or iface.startswith("rmnet")):
                continue
            return ip
    except Exception as e:
        logger.debug(f"Failed to get IP from route: {e}")

    # 2) wlan0 addr
    try:
        addr_out = await _run_async(adb_path, device_id, ["ip", "-4", "addr", "show", "wlan0"])
        ip = _extract_ip(addr_out)
        if ip:
            return ip
    except Exception as e:
        logger.debug(f"Failed to get IP from wlan0: {e}")

    return None


# ==================== Serial ====================

# Serial number properties to try, in order of preference
_SERIAL_PROPS = [
    "ro.serialno",
    "ro.boot.serialno",
    "ro.product.serial",
]


def extract_serial_from_mdns(device_id: str) -> str | None:
    """
    Extract hardware serial number from mDNS device ID.

    mDNS service names follow the pattern: adb-{serial}[-{suffix}].{service_type}

    Examples:
        - "adb-243a09b7-cbCO6P._adb-tls-connect._tcp" → "243a09b7"
        - "adb-243a09b7._adb._tcp" → "243a09b7"
        - "adb-ABC123DEF.local" → "ABC123DEF"

    Args:
        device_id: The device ID (can be mDNS service name or regular device ID)

    Returns:
        Extracted serial number, or None if not a valid mDNS format
    """
    # Check if this is an mDNS device ID
    mdns_indicators = [
        "._adb-tls-connect._tcp",
        "._adb-tls-pairing._tcp",
        "._adb._tcp",
        ".local",
    ]

    if not any(indicator in device_id for indicator in mdns_indicators):
        return None

    # Pattern: adb-{serial}[-{suffix}].{service_type}
    # Match alphanumeric characters (not just hex)
    pattern = r"adb-([0-9a-zA-Z]+)"
    match = re.search(pattern, device_id)

    if match:
        serial = match.group(1)
        # Validate serial format (alphanumeric, typically 6-16 chars)
        if len(serial) >= 6 and serial.isalnum():
            return serial

    return None


async def get_device_serial(device_id: str, adb_path: str = "adb") -> str:
    """
    Get the real hardware serial number of a device (async version).

    For mDNS devices, attempts to extract serial from service name first.
    Falls back to getprop for USB/WiFi devices or if extraction fails.
    If all methods fail, returns device_id as fallback (for emulators or
    restricted devices that don't expose serial number).

    This works for both USB and WiFi connected devices,
    returning the actual hardware serial number (ro.serialno).

    Args:
        device_id: The device ID (can be USB serial or IP:port for WiFi)
        adb_path: Path to adb executable (default: "adb")

    Returns:
        The device hardware serial number. Always returns a value - uses
        device_id as fallback if serial cannot be obtained.
    """
    # Fast path: Try mDNS extraction first
    mdns_serial = extract_serial_from_mdns(device_id)
    if mdns_serial:
        logger.debug(f"Extracted serial from mDNS name: {device_id} → {mdns_serial}")
        return mdns_serial

    # Try multiple serial properties (some emulators use different props)
    for prop in _SERIAL_PROPS:
        try:
            result = await run_cmd_silently(
                [adb_path, "-s", device_id, "shell", "getprop", prop],
            )
            if result.returncode == 0:
                serial = result.stdout.strip()
                # Filter out error messages and empty values
                if serial and not serial.startswith("error:") and serial != "unknown":
                    logger.debug(f"Got serial via {prop}: {device_id} → {serial}")
                    return serial
        except Exception as e:
            logger.debug(f"Failed to get serial via {prop} for {device_id}: {e}")
            continue

    # Fallback: Use device_id itself as serial
    logger.warning(
        f"Could not get hardware serial for {device_id}, "
        f"using device_id as serial (emulator/restricted device)"
    )
    return device_id


# ==================== Pairing ====================


async def pair_device(
    ip: str,
    port: int,
    pairing_code: str,
    adb_path: str = "adb",
) -> tuple[bool, str]:
    """
    Pair with Android device using wireless debugging (Android 11+) (async version).

    Args:
        ip: Device IP address
        port: Pairing port (NOT connection port, typically shown in "Pair device with code" dialog)
        pairing_code: 6-digit pairing code from device
        adb_path: Path to adb executable

    Returns:
        Tuple of (success, message)

    Example:
        >>> await pair_device("192.168.1.100", 37831, "197872")
        (True, "Successfully paired to 192.168.1.100:37831")
    """
    # Validate pairing code format (6 digits)
    if not pairing_code.isdigit() or len(pairing_code) != 6:
        return False, "Pairing code must be 6 digits"

    address = f"{ip}:{port}"

    try:
        # Execute: adb pair ip:port pairing_code
        result = await run_cmd_silently(
            [adb_path, "pair", address, pairing_code], timeout=30
        )

        output = result.stdout + result.stderr

        # Check for success indicators
        if "Successfully paired" in output or "success" in output.lower():
            return True, f"Successfully paired to {address}"
        elif "failed" in output.lower():
            # Extract error details
            if "pairing code" in output.lower():
                return False, "Invalid pairing code"
            elif "refused" in output.lower():
                return (
                    False,
                    "Connection refused - check if wireless debugging is enabled",
                )
            else:
                return False, f"Pairing failed: {output.strip()}"
        else:
            return False, output.strip() or "Unknown pairing error"

    except Exception as e:
        return False, f"Pairing error: {e}"
