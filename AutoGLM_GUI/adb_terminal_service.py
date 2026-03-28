"""Web terminal session management for interactive shell access."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import os
import secrets
import signal
import struct
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import is_windows

_DEFAULT_BUFFER_SIZE = 200
_DEFAULT_READ_CHUNK_SIZE = 4096
_DEFAULT_BUFFER_BYTES = 256 * 1024
_DEFAULT_MAX_OUTPUT_BYTES = 5 * 1024 * 1024


def _get_project_root() -> Path:
    """Return the AutoGLM project root directory."""
    return Path(__file__).resolve().parent.parent


def _resolve_default_shell_command() -> list[str]:
    """Return the default interactive ADB-only terminal command."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--adb-terminal-repl"]

    executable_name = Path(sys.executable).name.lower()
    if "python" not in executable_name:
        return [sys.executable, "--adb-terminal-repl"]

    return [sys.executable, "-m", "AutoGLM_GUI.adb_terminal_repl"]


def _detect_scrcpy_server_path() -> str | None:
    """Return the best available scrcpy-server path."""
    project_server = (
        _get_project_root() / "AutoGLM_GUI" / "resources" / "scrcpy-server-v3.3.3"
    )
    if project_server.exists():
        return str(project_server)

    scrcpy_server = os.environ.get("SCRCPY_SERVER_PATH")
    if scrcpy_server and Path(scrcpy_server).exists():
        return scrcpy_server

    return None


def _prepend_path_entries(env: dict[str, str], entries: list[Path]) -> None:
    """Prepend directories to PATH while preserving order and removing duplicates."""
    path_key = next((key for key in env if key.upper() == "PATH"), "PATH")
    separator = os.pathsep
    current_path = env.get(path_key, "")

    normalized_entries: list[str] = []
    seen = set()
    for entry in entries:
        entry_str = str(entry)
        if not entry_str or entry_str in seen:
            continue
        seen.add(entry_str)
        normalized_entries.append(entry_str)

    existing_parts = [part for part in current_path.split(separator) if part]
    filtered_existing = [part for part in existing_parts if part not in seen]
    env[path_key] = separator.join(normalized_entries + filtered_existing)


def _build_terminal_environment(project_root: Path) -> dict[str, str]:
    """Build the default environment for new terminal sessions."""
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["AUTOGLM_PROJECT_ROOT"] = str(project_root)

    path_entries: list[Path] = []

    adb_path = env.get("AUTOGLM_ADB_PATH")
    if adb_path:
        adb_binary = Path(adb_path).expanduser()
        if adb_binary.is_file():
            path_entries.append(adb_binary.parent)

    venv_root = project_root / ".venv"
    venv_bin_dir = venv_root / ("Scripts" if is_windows() else "bin")
    if venv_bin_dir.exists():
        env["VIRTUAL_ENV"] = str(venv_root)
        path_entries.append(venv_bin_dir)

    path_entries.append(project_root)
    _prepend_path_entries(env, path_entries)

    scrcpy_server_path = _detect_scrcpy_server_path()
    if scrcpy_server_path:
        env["SCRCPY_SERVER_PATH"] = scrcpy_server_path

    return env


def _hash_session_token(token: str) -> str:
    """Return a stable hash for a session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TerminalSession:
    """Single interactive terminal session."""

    def __init__(
        self,
        *,
        session_id: str,
        cwd: str,
        command: list[str],
        env: dict[str, str],
        created_by: str | None,
        origin: str | None,
        owner_token_hash: str,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
        max_buffer_bytes: int = _DEFAULT_BUFFER_BYTES,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.command = command
        self.env = env
        self.created_by = created_by
        self.origin = origin
        self.owner_token_hash = owner_token_hash
        self.status = "created"
        self.created_at = time.time()
        self.last_active_at = self.created_at
        self.exit_code: int | None = None
        self.total_output_bytes = 0

        self._buffer: deque[tuple[dict[str, Any], int]] = deque(maxlen=buffer_size)
        self._buffer_bytes = 0
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._process: subprocess.Popen[bytes] | asyncio.subprocess.Process | None = (
            None
        )
        self._master_fd: int | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._close_lock = asyncio.Lock()
        self._max_buffer_bytes = max_buffer_bytes
        self._max_output_bytes = max_output_bytes
        self._output_limit_triggered = False

    def to_response(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "command": list(self.command),
            "status": self.status,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "exit_code": self.exit_code,
            "created_by": self.created_by,
            "origin": self.origin,
            "owner_token_hash": self.owner_token_hash,
            "total_output_bytes": self.total_output_bytes,
        }

    def subscribe(self) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue, [event for event, _ in self._buffer]

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
        try:
            process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                env=self.env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )
        except Exception:
            with contextlib.suppress(OSError):
                os.close(master_fd)
            with contextlib.suppress(OSError):
                os.close(slave_fd)
            raise

        os.close(slave_fd)

        self._master_fd = master_fd
        self._process = process
        self._reader_task = asyncio.create_task(self._read_posix_output())
        self._wait_task = asyncio.create_task(self._wait_for_process())

    async def _start_windows(self) -> None:
        process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            env=self.env,
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

            if not await self._publish_output("stdout", chunk):
                return

    async def _read_windows_output(self) -> None:
        process = self._windows_process
        if process is None or process.stdout is None:
            return

        while True:
            chunk = await process.stdout.read(_DEFAULT_READ_CHUNK_SIZE)
            if not chunk:
                return

            if not await self._publish_output("stdout", chunk):
                return

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
        current_task = asyncio.current_task()

        if self._reader_task is not None:
            self._reader_task.cancel()
            if self._reader_task is not current_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await self._reader_task
            self._reader_task = None

        if self._wait_task is not None:
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
        self._append_to_buffer(event, self._estimate_event_size(event))
        dead_queues: list[asyncio.Queue[dict[str, Any]]] = []

        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except RuntimeError:
                dead_queues.append(queue)

        for queue in dead_queues:
            self._subscribers.discard(queue)

    async def _publish_output(self, stream: str, chunk: bytes) -> bool:
        chunk_size = len(chunk)
        if self.total_output_bytes + chunk_size > self._max_output_bytes:
            if not self._output_limit_triggered:
                self._output_limit_triggered = True
                await self._publish(
                    {
                        "type": "error",
                        "message": "Terminal output limit exceeded. Session will be closed.",
                    }
                )
                asyncio.create_task(self.close())
            return False

        self.total_output_bytes += chunk_size
        await self._publish(
            {
                "type": "output",
                "stream": stream,
                "data": chunk.decode("utf-8", errors="replace"),
            }
        )
        return True

    def _append_to_buffer(self, event: dict[str, Any], event_size: int) -> None:
        if self._buffer.maxlen is not None and len(self._buffer) == self._buffer.maxlen:
            _, removed_size = self._buffer.popleft()
            self._buffer_bytes -= removed_size

        self._buffer.append((event, event_size))
        self._buffer_bytes += event_size

        while self._buffer and self._buffer_bytes > self._max_buffer_bytes:
            _, removed_size = self._buffer.popleft()
            self._buffer_bytes -= removed_size

    def _estimate_event_size(self, event: dict[str, Any]) -> int:
        payload = event.get("data")
        if isinstance(payload, str):
            return len(payload.encode("utf-8", errors="replace")) + 128
        message = event.get("message")
        if isinstance(message, str):
            return len(message.encode("utf-8", errors="replace")) + 128
        return 256

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
        self._session_token_hashes: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        *,
        cwd: str | None = None,
        command: list[str] | None = None,
        created_by: str | None = None,
        origin: str | None = None,
    ) -> tuple[TerminalSession, str]:
        project_root = _get_project_root()
        resolved_cwd = str(Path(cwd or project_root).expanduser().resolve())
        if not Path(resolved_cwd).exists():
            raise ValueError(f"Working directory does not exist: {resolved_cwd}")
        if not Path(resolved_cwd).is_dir():
            raise ValueError(f"Working directory is not a directory: {resolved_cwd}")

        if command is not None:
            raise ValueError("Custom terminal commands are disabled in ADB-only mode")

        resolved_command = _resolve_default_shell_command()

        session_token = secrets.token_urlsafe(32)
        owner_token_hash = _hash_session_token(session_token)

        session = TerminalSession(
            session_id=uuid.uuid4().hex,
            cwd=resolved_cwd,
            command=resolved_command,
            env=_build_terminal_environment(project_root),
            created_by=created_by,
            origin=origin,
            owner_token_hash=owner_token_hash,
        )

        async with self._lock:
            self._sessions[session.session_id] = session
            self._session_token_hashes[session.session_id] = owner_token_hash

        try:
            await session.start()
        except Exception:
            async with self._lock:
                self._sessions.pop(session.session_id, None)
                self._session_token_hashes.pop(session.session_id, None)
            raise

        logger.info(
            "Created terminal session %s with cwd=%s command=%s",
            session.session_id,
            session.cwd,
            session.command,
        )
        return session, session_token

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            self._session_token_hashes.pop(session_id, None)

        if session is None:
            return False

        await session.close()
        logger.info("Closed terminal session %s", session_id)
        return True

    def get_session(self, session_id: str) -> TerminalSession | None:
        return self._sessions.get(session_id)

    def authenticate_session(
        self, session_id: str, session_token: str | None
    ) -> TerminalSession | None:
        if not session_token:
            return None

        session = self._sessions.get(session_id)
        expected_hash = self._session_token_hashes.get(session_id)
        if session is None or expected_hash is None:
            return None

        provided_hash = _hash_session_token(session_token)
        if not hmac.compare_digest(provided_hash, expected_hash):
            return None

        return session


terminal_session_manager = TerminalSessionManager()
