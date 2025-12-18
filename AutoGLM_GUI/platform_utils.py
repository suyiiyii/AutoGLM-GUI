"""Platform-aware subprocess helpers to avoid duplicated Windows branches."""

import asyncio
import platform
import subprocess
from typing import Any, Sequence


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


async def spawn_process(cmd: Sequence[str], *, capture_output: bool = False) -> Any:
    """Start a long-running process with optional stdio capture."""
    stdout = subprocess.PIPE if capture_output else None
    stderr = subprocess.PIPE if capture_output else None

    if is_windows():
        return subprocess.Popen(cmd, stdout=stdout, stderr=stderr)

    return await asyncio.create_subprocess_exec(*cmd, stdout=stdout, stderr=stderr)
