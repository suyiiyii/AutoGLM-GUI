"""Get device serial number using ADB."""

import re
from typing import Optional

from AutoGLM_GUI.platform_utils import run_cmd_silently_sync


def extract_serial_from_mdns(device_id: str) -> Optional[str]:
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
    # The serial is everything after "adb-" until the next hyphen or dot
    # Match alphanumeric characters (not just hex)
    pattern = r"adb-([0-9a-zA-Z]+)"
    match = re.search(pattern, device_id)

    if match:
        serial = match.group(1)
        # Validate serial format (alphanumeric, typically 6-16 chars)
        if len(serial) >= 6 and serial.isalnum():
            return serial

    return None


def get_device_serial(device_id: str, adb_path: str = "adb") -> str | None:
    """
    Get the real hardware serial number of a device.

    For mDNS devices, attempts to extract serial from service name first.
    Falls back to getprop for USB/WiFi devices or if extraction fails.
    For emulators and special devices, uses device_id as fallback.

    This works for both USB and WiFi connected devices,
    returning the actual hardware serial number (ro.serialno).

    Args:
        device_id: The device ID (can be USB serial or IP:port for WiFi)
        adb_path: Path to adb executable (default: "adb")

    Returns:
        The device hardware serial number, or None if failed
    """
    from AutoGLM_GUI.logger import logger

    # Fast path: Try mDNS extraction first
    mdns_serial = extract_serial_from_mdns(device_id)
    if mdns_serial:
        logger.debug(f"Extracted serial from mDNS name: {device_id} → {mdns_serial}")
        return mdns_serial

    # Try multiple methods to get serial
    serial = None

    # Method 1: Use getprop ro.serialno
    try:
        result = run_cmd_silently_sync(
            [adb_path, "-s", device_id, "shell", "getprop", "ro.serialno"],
            timeout=5,
        )
        if result.returncode == 0:
            serial = result.stdout.strip()
            if serial and not serial.startswith("error:") and serial != "unknown" and serial != "":
                logger.debug(f"Got serial via ro.serialno: {device_id} → {serial}")
                return serial
    except Exception as e:
        logger.debug(f"Failed to get serial via ro.serialno for {device_id}: {e}")

    # Method 2: Try ro.boot.serialno (some devices use this)
    try:
        result = run_cmd_silently_sync(
            [adb_path, "-s", device_id, "shell", "getprop", "ro.boot.serialno"],
            timeout=5,
        )
        if result.returncode == 0:
            serial = result.stdout.strip()
            if serial and not serial.startswith("error:") and serial != "unknown" and serial != "":
                logger.debug(f"Got serial via ro.boot.serialno: {device_id} → {serial}")
                return serial
    except Exception as e:
        logger.debug(f"Failed to get serial via ro.boot.serialno for {device_id}: {e}")

    # Method 3: Try emu.uuid for emulators
    try:
        result = run_cmd_silently_sync(
            [adb_path, "-s", device_id, "shell", "getprop", "emu.uuid"],
            timeout=5,
        )
        if result.returncode == 0:
            serial = result.stdout.strip()
            if serial and not serial.startswith("error:") and serial != "":
                logger.debug(f"Got serial via emu.uuid: {device_id} → {serial}")
                return serial
    except Exception as e:
        logger.debug(f"Failed to get serial via emu.uuid for {device_id}: {e}")

    # Method 4: For emulators and localhost connections, use device_id as serial
    # This handles cases like 127.0.0.1:16384, emulator-5554, etc.
    if _is_emulator_or_localhost(device_id):
        # Use a sanitized version of device_id as serial
        sanitized_serial = device_id.replace(":", "_").replace(".", "_")
        logger.debug(f"Using device_id as serial for emulator/localhost: {device_id} → {sanitized_serial}")
        return sanitized_serial

    # Method 5: Last resort - try to get any unique identifier
    try:
        result = run_cmd_silently_sync(
            [adb_path, "-s", device_id, "shell", "settings", "get", "secure", "android_id"],
            timeout=5,
        )
        if result.returncode == 0:
            serial = result.stdout.strip()
            if serial and not serial.startswith("error:") and serial != "null" and serial != "":
                logger.debug(f"Got serial via android_id: {device_id} → {serial}")
                return serial
    except Exception as e:
        logger.debug(f"Failed to get serial via android_id for {device_id}: {e}")

    logger.warning(f"Could not get serial for device {device_id}, all methods failed")
    return None


def _is_emulator_or_localhost(device_id: str) -> bool:
    """
    Check if the device_id represents an emulator or localhost connection.
    
    Args:
        device_id: The device ID to check
        
    Returns:
        True if it's an emulator or localhost connection
    """
    emulator_patterns = [
        "emulator-",
        "127.0.0.1:",
        "localhost:",
        "10.0.2.2:",  # Android emulator host
    ]
    return any(device_id.startswith(pattern) for pattern in emulator_patterns)
