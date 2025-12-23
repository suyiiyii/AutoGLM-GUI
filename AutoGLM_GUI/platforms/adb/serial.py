"""Get device serial number using ADB."""

from AutoGLM_GUI.platform_utils import run_cmd_silently_sync


def get_device_serial(device_id: str, adb_path: str = "adb") -> str | None:
    """
    Get the real hardware serial number of a device.

    This works for both USB and WiFi connected devices,
    returning the actual hardware serial number (ro.serialno).

    Args:
        device_id: The device ID (can be USB serial or IP:port for WiFi)
        adb_path: Path to adb executable (default: "adb")

    Returns:
        The device hardware serial number, or None if failed
    """
    try:
        # Use getprop to get the actual hardware serial number
        # This works for both USB and WiFi connections
        result = run_cmd_silently_sync(
            [adb_path, "-s", device_id, "shell", "getprop", "ro.serialno"],
            timeout=3,
        )
        if result.returncode == 0:
            serial = result.stdout.strip()
            # Filter out error messages and empty values
            if serial and not serial.startswith("error:") and serial != "unknown":
                return serial
    except Exception:
        pass

    return None
