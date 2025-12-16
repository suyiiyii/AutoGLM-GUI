"""Platform-aware subprocess helpers to avoid duplicated Windows branches."""

import asyncio
import platform
import subprocess
from typing import Any, Sequence


def is_windows() -> bool:
    """Return True if running on Windows."""
    return platform.system() == "Windows"


async def run_cmd_silently(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    """Run a command, suppressing output; safe for async contexts on all platforms."""
    if is_windows():
        # Avoid blocking the event loop with a blocking subprocess call on Windows.
        return await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, check=False
        )

    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    await process.wait()
    return subprocess.CompletedProcess(cmd, process.returncode, None, None)


async def spawn_process(cmd: Sequence[str], *, capture_output: bool = False) -> Any:
    """Start a long-running process with optional stdio capture."""
    stdout = subprocess.PIPE if capture_output else None
    stderr = subprocess.PIPE if capture_output else None

    if is_windows():
        return subprocess.Popen(cmd, stdout=stdout, stderr=stderr)

    return await asyncio.create_subprocess_exec(*cmd, stdout=stdout, stderr=stderr)
