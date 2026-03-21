"""ADB wireless pairing support for Android 11+."""

from AutoGLM_GUI.platform_utils import run_cmd_silently, run_cmd_silently_sync


def pair_device(
    ip: str,
    port: int,
    pairing_code: str,
    adb_path: str = "adb",
) -> tuple[bool, str]:
    """
    Pair with Android device using wireless debugging (Android 11+).

    Args:
        ip: Device IP address
        port: Pairing port (NOT connection port, typically shown in "Pair device with code" dialog)
        pairing_code: 6-digit pairing code from device
        adb_path: Path to adb executable

    Returns:
        Tuple of (success, message)

    Example:
        >>> pair_device("192.168.1.100", 37831, "197872")
        (True, "Successfully paired to 192.168.1.100:37831")
    """
    # Validate pairing code format (6 digits)
    if not pairing_code.isdigit() or len(pairing_code) != 6:
        return False, "Pairing code must be 6 digits"

    address = f"{ip}:{port}"

    try:
        # Execute: adb pair ip:port pairing_code
        result = run_cmd_silently_sync(
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


async def pair_device_async(
    ip: str,
    port: int,
    pairing_code: str,
    adb_path: str = "adb",
) -> tuple[bool, str]:
    """Async variant of ``pair_device`` for request flows."""
    if not pairing_code.isdigit() or len(pairing_code) != 6:
        return False, "Pairing code must be 6 digits"

    address = f"{ip}:{port}"

    try:
        result = await run_cmd_silently(
            [adb_path, "pair", address, pairing_code],
            timeout=30,
        )
        output = result.stdout + result.stderr

        if "Successfully paired" in output or "success" in output.lower():
            return True, f"Successfully paired to {address}"
        if "failed" in output.lower():
            if "pairing code" in output.lower():
                return False, "Invalid pairing code"
            if "refused" in output.lower():
                return (
                    False,
                    "Connection refused - check if wireless debugging is enabled",
                )
            return False, f"Pairing failed: {output.strip()}"
        return False, output.strip() or "Unknown pairing error"
    except Exception as exc:
        return False, f"Pairing error: {exc}"
