"""Platform-aware subprocess helpers to avoid duplicated Windows branches."""

import asyncio
import platform
import subprocess
from asyncio.subprocess import Process as AsyncProcess
from typing import Sequence


def is_windows() -> bool:
    """Return True if running on Windows."""
    return platform.system() == "Windows"


def run_cmd_silently_sync(
    cmd: Sequence[str], timeout: float | None = None
) -> subprocess.CompletedProcess:
    """Run a command synchronously, suppressing output but preserving it in the result.

    This is the synchronous version that works on all platforms.

    Args:
        cmd: Command to run as a sequence of strings
        timeout: Optional timeout in seconds

    Returns:
        CompletedProcess with stdout/stderr captured
    """
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, timeout=timeout
    )


async def run_cmd_silently(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    """Run a command, suppressing output but preserving it in the result; safe for async contexts on all platforms."""
    if is_windows():
        # Avoid blocking the event loop with a blocking subprocess call on Windows.
        return await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, check=False
        )

    # Use PIPE on macOS/Linux to capture output
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    # Decode bytes to string for API consistency across platforms
    stdout_str = stdout.decode("utf-8") if stdout else ""
    stderr_str = stderr.decode("utf-8") if stderr else ""
    # Return CompletedProcess with stdout/stderr for API consistency across platforms
    return_code = process.returncode if process.returncode is not None else -1
    return subprocess.CompletedProcess(cmd, return_code, stdout_str, stderr_str)


async def spawn_process(
    cmd: Sequence[str], *, capture_output: bool = False
) -> subprocess.Popen[bytes] | AsyncProcess:
    """Start a long-running process with optional stdio capture."""
    stdout = subprocess.PIPE if capture_output else None
    stderr = subprocess.PIPE if capture_output else None

    if is_windows():
        return subprocess.Popen(cmd, stdout=stdout, stderr=stderr)

    return await asyncio.create_subprocess_exec(*cmd, stdout=stdout, stderr=stderr)


def build_adb_command(device_id: str | None = None, adb_path: str = "adb") -> list[str]:
    """Build ADB command prefix with optional device specifier.

    This centralizes the logic for constructing ADB commands across all modules.

    Args:
        device_id: Optional ADB device serial (e.g., "192.168.1.100:5555" or USB serial)
        adb_path: Path to ADB executable (default: "adb")

    Returns:
        List of command parts to use with subprocess (e.g., ["adb", "-s", "device_id"])

    Examples:
        >>> build_adb_command()
        ['adb']
        >>> build_adb_command(device_id="192.168.1.100:5555")
        ['adb', '-s', '192.168.1.100:5555']
        >>> build_adb_command(device_id="emulator-5554", adb_path="/usr/local/bin/adb")
        ['/usr/local/bin/adb', '-s', 'emulator-5554']
    """
    cmd = [adb_path]
    if device_id:
        cmd.extend(["-s", device_id])
    return cmd
