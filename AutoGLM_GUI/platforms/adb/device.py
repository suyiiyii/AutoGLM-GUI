"""Device availability checking utilities."""

import asyncio

from AutoGLM_GUI.exceptions import DeviceNotAvailableError
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import run_cmd_silently


async def check_device_available(device_id: str | None = None) -> None:
    """Check if the device is available.

    Args:
        device_id: ADB device serial (None for default device)

    Raises:
        DeviceNotAvailableError: If device is not reachable
    """
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.append("get-state")

    try:
        result = await asyncio.wait_for(run_cmd_silently(cmd), timeout=5.0)

        state = result.stdout.strip() if result.stdout else ""
        error_output = result.stderr.strip() if result.stderr else ""

        # Check for common error patterns
        if "not found" in error_output.lower() or "offline" in error_output.lower():
            raise DeviceNotAvailableError(
                f"Device {device_id} is not available: {error_output}"
            )

        if state != "device":
            raise DeviceNotAvailableError(
                f"Device {device_id} is not available (state: {state or 'offline'})"
            )

        logger.debug(f"Device {device_id} is available (state: {state})")

    except asyncio.TimeoutError:
        raise DeviceNotAvailableError(f"Device {device_id} connection timed out")
    except FileNotFoundError:
        raise DeviceNotAvailableError("ADB executable not found")
    except DeviceNotAvailableError:
        raise
    except Exception as e:
        raise DeviceNotAvailableError(f"Failed to check device {device_id}: {e}")
