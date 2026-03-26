"""Web terminal session management for interactive shell access."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import struct
import subprocess
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import is_windows

_DEFAULT_BUFFER_SIZE = 200
_DEFAULT_READ_CHUNK_SIZE = 4096


def _resolve_default_shell_command() -> list[str]:
    """Return the default interactive shell command."""
    if is_windows():
        comspec = os.environ.get("COMSPEC")
        if comspec:
            return [comspec]
        return ["cmd.exe"]

    shell = os.environ.get("SHELL")
    if shell:
        return [shell, "-i"]

    for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
        if Path(candidate).exists():
            return [candidate, "-i"]

    resolved_shell = shutil.which("zsh") or shutil.which("bash") or shutil.which("sh")
    if resolved_shell:
        return [resolved_shell, "-i"]

    return ["/bin/sh", "-i"]


class TerminalSession:
    """Single interactive terminal session."""

    def __init__(
        self,
        *,
        session_id: str,
        cwd: str,
        command: list[str],
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.command = command
        self.status = "created"
        self.created_at = time.time()
        self.last_active_at = self.created_at
        self.exit_code: int | None = None

        self._buffer: deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._process: subprocess.Popen[bytes] | asyncio.subprocess.Process | None = (
            None
        )
        self._master_fd: int | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._close_lock = asyncio.Lock()

    def to_response(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "command": list(self.command),
            "status": self.status,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "exit_code": self.exit_code,
        }

    def subscribe(self) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue, list(self._buffer)

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def start(self) -> None:
        if self.status not in {"created", "closed", "error"}:
            return

        try:
            self.status = "starting"
            await self._publish({"type": "status", "status": self.status})

            if is_windows():
                await self._start_windows()
            else:
                await self._start_posix()

            self.status = "running"
            self.last_active_at = time.time()
            await self._publish({"type": "status", "status": self.status})
        except Exception as exc:
            self.status = "error"
            self.exit_code = -1
            logger.exception("Failed to start terminal session %s", self.session_id)
            await self._publish({"type": "error", "message": str(exc)})
            await self._publish({"type": "status", "status": self.status})
            raise

    async def write(self, data: str) -> None:
        if not data or self.status != "running":
            return

        self.last_active_at = time.time()
        encoded = data.encode("utf-8", errors="replace")

        if is_windows():
            process = self._windows_process
            if process is None or process.stdin is None:
                return
            process.stdin.write(encoded)
            await process.stdin.drain()
            return

        if self._master_fd is None:
            return

        await asyncio.to_thread(os.write, self._master_fd, encoded)

    async def resize(self, cols: int, rows: int) -> None:
        cols = max(1, cols)
        rows = max(1, rows)

        master_fd = self._master_fd
        if is_windows() or master_fd is None:
            return

        def _resize_pty() -> None:
            import fcntl
            import termios

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        await asyncio.to_thread(_resize_pty)

    async def close(self) -> None:
        async with self._close_lock:
            if self.status in {"closed", "terminating"}:
                return

            self.status = "terminating"
            await self._publish({"type": "status", "status": self.status})

            try:
                await self._terminate_process()
            finally:
                await self._finalize_close()

    async def _start_posix(self) -> None:
        import pty

        master_fd, slave_fd = pty.openpty()
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")

        process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)

        self._master_fd = master_fd
        self._process = process
        self._reader_task = asyncio.create_task(self._read_posix_output())
        self._wait_task = asyncio.create_task(self._wait_for_process())

    async def _start_windows(self) -> None:
        process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._process = process
        self._reader_task = asyncio.create_task(self._read_windows_output())
        self._wait_task = asyncio.create_task(self._wait_for_process())

    async def _read_posix_output(self) -> None:
        while True:
            if self._master_fd is None:
                return

            try:
                chunk = await asyncio.to_thread(
                    os.read, self._master_fd, _DEFAULT_READ_CHUNK_SIZE
                )
            except OSError:
                return

            if not chunk:
                return

            await self._publish(
                {
                    "type": "output",
                    "stream": "stdout",
                    "data": chunk.decode("utf-8", errors="replace"),
                }
            )

    async def _read_windows_output(self) -> None:
        process = self._windows_process
        if process is None or process.stdout is None:
            return

        while True:
            chunk = await process.stdout.read(_DEFAULT_READ_CHUNK_SIZE)
            if not chunk:
                return

            await self._publish(
                {
                    "type": "output",
                    "stream": "stdout",
                    "data": chunk.decode("utf-8", errors="replace"),
                }
            )

    async def _wait_for_process(self) -> None:
        exit_code: int

        if is_windows():
            process = self._windows_process
            if process is None:
                return
            exit_code = await process.wait()
        else:
            process = self._posix_process
            if process is None:
                return
            exit_code = await asyncio.to_thread(process.wait)

        self.exit_code = exit_code
        await self._publish({"type": "exit", "exit_code": exit_code})

        if self.status not in {"closed", "terminating"}:
            await self._finalize_close()

    async def _terminate_process(self) -> None:
        if is_windows():
            process = self._windows_process
            if process is None:
                return
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            return

        process = self._posix_process
        if process is None:
            return

        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)

        try:
            await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=2.0)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await asyncio.to_thread(process.wait)

    async def _finalize_close(self) -> None:
        if self.status == "closed":
            return

        self.status = "closed"
        self.last_active_at = time.time()

        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        if self._wait_task is not None:
            current_task = asyncio.current_task()
            if self._wait_task is not current_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await self._wait_task
            self._wait_task = None

        if self._master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._master_fd)
            self._master_fd = None

        await self._publish({"type": "status", "status": self.status})

    async def _publish(self, event: dict[str, Any]) -> None:
        self._buffer.append(event)
        dead_queues: list[asyncio.Queue[dict[str, Any]]] = []

        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except RuntimeError:
                dead_queues.append(queue)

        for queue in dead_queues:
            self._subscribers.discard(queue)

    @property
    def _posix_process(self) -> subprocess.Popen[bytes] | None:
        if isinstance(self._process, subprocess.Popen):
            return self._process
        return None

    @property
    def _windows_process(self) -> asyncio.subprocess.Process | None:
        if isinstance(self._process, asyncio.subprocess.Process):
            return self._process
        return None


class TerminalSessionManager:
    """In-memory registry of web terminal sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        *,
        cwd: str | None = None,
        command: list[str] | None = None,
    ) -> TerminalSession:
        resolved_cwd = str(Path(cwd or os.getcwd()).expanduser().resolve())
        if not Path(resolved_cwd).exists():
            raise ValueError(f"Working directory does not exist: {resolved_cwd}")
        if not Path(resolved_cwd).is_dir():
            raise ValueError(f"Working directory is not a directory: {resolved_cwd}")

        resolved_command = command or _resolve_default_shell_command()
        if not resolved_command:
            raise ValueError("Command cannot be empty")

        session = TerminalSession(
            session_id=uuid.uuid4().hex,
            cwd=resolved_cwd,
            command=resolved_command,
        )

        async with self._lock:
            self._sessions[session.session_id] = session

        await session.start()
        logger.info(
            "Created terminal session %s with cwd=%s command=%s",
            session.session_id,
            session.cwd,
            session.command,
        )
        return session

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is None:
            return False

        await session.close()
        logger.info("Closed terminal session %s", session_id)
        return True

    def get_session(self, session_id: str) -> TerminalSession | None:
        return self._sessions.get(session_id)


terminal_session_manager = TerminalSessionManager()
