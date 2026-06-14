"""Unit tests for terminal session defaults."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import AutoGLM_GUI.adb_terminal_service as terminal_service


def _session(**kwargs: object) -> terminal_service.TerminalSession:
    defaults = {
        "session_id": "terminal-1",
        "cwd": "/tmp",
        "command": ["/bin/sh"],
        "env": {"TERM": "xterm-256color"},
        "created_by": "127.0.0.1",
        "origin": "http://localhost:3000",
        "owner_token_hash": "token-hash",
    }
    defaults.update(kwargs)
    return terminal_service.TerminalSession(**defaults)


def test_build_terminal_environment_includes_project_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    venv_bin = project_root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)

    adb_bin = tmp_path / "platform-tools" / "adb"
    adb_bin.parent.mkdir(parents=True)
    adb_bin.write_text("", encoding="utf-8")

    scrcpy_server = project_root / "AutoGLM_GUI" / "resources" / "scrcpy-server-v3.3.3"
    scrcpy_server.parent.mkdir(parents=True)
    scrcpy_server.write_text("", encoding="utf-8")

    monkeypatch.setenv("AUTOGLM_ADB_PATH", str(adb_bin))
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(terminal_service, "_get_project_root", lambda: project_root)

    env = terminal_service._build_terminal_environment(project_root)

    assert env["AUTOGLM_PROJECT_ROOT"] == str(project_root)
    assert env["AUTOGLM_ADB_PATH"] == str(adb_bin)
    assert env["SCRCPY_SERVER_PATH"] == str(scrcpy_server)
    assert env["VIRTUAL_ENV"] == str(project_root / ".venv")
    assert env["TERM"] == "xterm-256color"

    path_parts = env["PATH"].split(":")
    assert path_parts[0] == str(adb_bin.parent)
    assert path_parts[1] == str(venv_bin)
    assert path_parts[2] == str(project_root)
    assert "/usr/bin" in path_parts


def test_resolve_default_shell_command_uses_cli_flag_for_non_python_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal_service.sys, "executable", "/tmp/autoglm-gui")

    command = terminal_service._resolve_default_shell_command()

    assert command == ["/tmp/autoglm-gui", "--adb-terminal-repl"]


def test_terminal_helpers_cover_frozen_python_env_and_path_dedup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(terminal_service.sys, "frozen", True, raising=False)
    monkeypatch.setattr(terminal_service.sys, "executable", "/tmp/app")
    assert terminal_service._resolve_default_shell_command() == [
        "/tmp/app",
        "--adb-terminal-repl",
    ]

    monkeypatch.setattr(terminal_service.sys, "frozen", False, raising=False)
    monkeypatch.setattr(terminal_service.sys, "executable", "/tmp/python3")
    assert terminal_service._resolve_default_shell_command() == [
        "/tmp/python3",
        "-m",
        "AutoGLM_GUI.adb_terminal_repl",
    ]

    env_server = tmp_path / "scrcpy-server"
    env_server.write_text("server", encoding="utf-8")
    monkeypatch.setattr(
        terminal_service,
        "_get_project_root",
        lambda: tmp_path / "missing-project",
    )
    monkeypatch.setenv("SCRCPY_SERVER_PATH", str(env_server))
    assert terminal_service._detect_scrcpy_server_path() == str(env_server)

    env = {"path": f"{tmp_path / 'a'}:{tmp_path / 'old'}:{tmp_path / 'a'}"}
    terminal_service._prepend_path_entries(
        env,
        [tmp_path / "a", tmp_path / "b", tmp_path / "a", Path("")],
    )
    assert env["path"].split(":") == [
        str(tmp_path / "a"),
        str(tmp_path / "b"),
        ".",
        str(tmp_path / "old"),
    ]


@pytest.mark.anyio
async def test_create_session_defaults_to_project_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    captured: dict[str, object] = {}

    async def fake_start(self: terminal_service.TerminalSession) -> None:
        captured["cwd"] = self.cwd
        captured["env"] = self.env
        self.status = "running"

    monkeypatch.setattr(terminal_service, "_get_project_root", lambda: project_root)
    monkeypatch.setattr(terminal_service.TerminalSession, "start", fake_start)

    manager = terminal_service.TerminalSessionManager()
    session, session_token = await manager.create_session(created_by="127.0.0.1")

    assert session.cwd == str(project_root)
    assert isinstance(session_token, str)
    assert captured["cwd"] == str(project_root)
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["AUTOGLM_PROJECT_ROOT"] == str(project_root)
    assert session.owner_token_hash == terminal_service._hash_session_token(
        session_token
    )
    assert manager.authenticate_session(session.session_id, session_token) is session


@pytest.mark.anyio
async def test_create_session_rejects_custom_command() -> None:
    manager = terminal_service.TerminalSessionManager()

    with pytest.raises(ValueError, match="ADB-only mode"):
        await manager.create_session(command=["/bin/zsh", "-i"])


@pytest.mark.anyio
async def test_create_session_removes_registry_entries_when_start_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    async def fake_start(self: terminal_service.TerminalSession) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(terminal_service, "_get_project_root", lambda: project_root)
    monkeypatch.setattr(terminal_service.TerminalSession, "start", fake_start)

    manager = terminal_service.TerminalSessionManager()

    with pytest.raises(RuntimeError, match="boom"):
        await manager.create_session(created_by="127.0.0.1")

    assert manager._sessions == {}
    assert manager._session_token_hashes == {}


@pytest.mark.anyio
async def test_create_session_validates_cwd_and_manager_auth_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = terminal_service.TerminalSessionManager()
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="does not exist"):
        await manager.create_session(cwd=str(missing))

    not_dir = tmp_path / "file"
    not_dir.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        await manager.create_session(cwd=str(not_dir))

    async def fake_close(self: terminal_service.TerminalSession) -> None:
        self.status = "closed"

    session = _session()
    token = "secret"
    session.owner_token_hash = terminal_service._hash_session_token(token)
    manager._sessions[session.session_id] = session
    manager._session_token_hashes[session.session_id] = session.owner_token_hash
    monkeypatch.setattr(terminal_service.TerminalSession, "close", fake_close)

    assert manager.get_session(session.session_id) is session
    assert manager.authenticate_session(session.session_id, None) is None
    assert manager.authenticate_session(session.session_id, "wrong") is None
    assert manager.authenticate_session("missing", token) is None
    assert manager.authenticate_session(session.session_id, token) is session
    assert await manager.close_session("missing") is False
    assert await manager.close_session(session.session_id) is True
    assert session.status == "closed"


@pytest.mark.anyio
async def test_terminal_output_limit_triggers_close() -> None:
    session = _session(max_output_bytes=4)

    closed = asyncio.Event()

    async def fake_close() -> None:
        closed.set()

    session.close = fake_close  # type: ignore[method-assign]

    published = await session._publish_output("stdout", b"12345")

    assert published is False
    assert session.total_output_bytes == 0
    assert session._output_limit_triggered is True
    assert closed.is_set() is False

    await asyncio.sleep(0)

    assert closed.is_set() is True


def test_append_to_buffer_accounts_for_deque_auto_eviction() -> None:
    session = _session(buffer_size=2, max_buffer_bytes=4096)

    first = {"type": "output", "data": "first"}
    second = {"type": "output", "data": "second"}
    third = {"type": "output", "data": "third"}

    first_size = session._estimate_event_size(first)
    second_size = session._estimate_event_size(second)
    third_size = session._estimate_event_size(third)

    session._append_to_buffer(first, first_size)
    session._append_to_buffer(second, second_size)
    session._append_to_buffer(third, third_size)

    assert [event for event, _ in session._buffer] == [second, third]
    assert session._buffer_bytes == second_size + third_size


@pytest.mark.anyio
async def test_terminal_session_publish_buffer_response_and_subscribers() -> None:
    session = _session(buffer_size=10, max_buffer_bytes=300)
    session.exit_code = 0
    response = session.to_response()
    assert response["session_id"] == "terminal-1"
    assert response["exit_code"] == 0

    await session._publish_output("stdout", b"hello")
    queue, replay = session.subscribe()
    assert replay[-1]["data"] == "hello"

    class BadQueue:
        def put_nowait(self, event: dict[str, object]) -> None:
            raise RuntimeError("closed")

    bad_queue = BadQueue()
    session._subscribers.add(bad_queue)  # type: ignore[arg-type]
    await session._publish({"type": "notice", "message": "world"})
    assert await queue.get() == {"type": "notice", "message": "world"}
    assert bad_queue not in session._subscribers
    session.unsubscribe(queue)
    assert queue not in session._subscribers

    session._append_to_buffer({"type": "output", "data": "x" * 400}, 528)
    assert session._buffer_bytes <= session._max_buffer_bytes
    assert session._estimate_event_size({"type": "status", "status": "running"}) == 256


@pytest.mark.anyio
async def test_terminal_session_start_write_resize_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    published: list[dict[str, object]] = []

    async def fake_publish(event: dict[str, object]) -> None:
        published.append(event)

    async def fake_start_posix() -> None:
        session._master_fd = 99

    monkeypatch.setattr(session, "_publish", fake_publish)
    monkeypatch.setattr(session, "_start_posix", fake_start_posix)
    monkeypatch.setattr(terminal_service, "is_windows", lambda: False)

    await session.start()
    await session.start()
    assert session.status == "running"
    assert [event["status"] for event in published if event["type"] == "status"] == [
        "starting",
        "running",
    ]

    written: list[tuple[int, bytes]] = []
    monkeypatch.setattr(
        terminal_service.os,
        "write",
        lambda fd, data: written.append((fd, data)) or len(data),
    )
    await session.write("")
    await session.write("abc")
    assert written == [(99, b"abc")]

    import fcntl

    resized: list[tuple[int, int]] = []
    monkeypatch.setattr(
        fcntl,
        "ioctl",
        lambda fd, request, data: resized.append((fd, len(data))),
    )
    await session.resize(0, 0)
    assert resized == [(99, 8)]

    error_session = _session(session_id="terminal-error")

    async def failing_start() -> None:
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(error_session, "_start_posix", failing_start)
    monkeypatch.setattr(error_session, "_publish", fake_publish)
    with pytest.raises(RuntimeError, match="spawn failed"):
        await error_session.start()
    assert error_session.status == "error"
    assert error_session.exit_code == -1


@pytest.mark.anyio
async def test_terminal_windows_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.data = b""

        def write(self, data: bytes) -> None:
            self.data += data

        async def drain(self) -> None:
            return None

    class FakeStdout:
        def __init__(self, chunks: list[bytes]) -> None:
            self.chunks = chunks

        async def read(self, size: int) -> bytes:
            return self.chunks.pop(0) if self.chunks else b""

    class FakeWindowsProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.stdout = FakeStdout([b"win-out", b""])
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            self.wait_calls += 1
            return 7

    monkeypatch.setattr(
        terminal_service.asyncio.subprocess, "Process", FakeWindowsProcess
    )
    monkeypatch.setattr(terminal_service, "is_windows", lambda: True)

    created_process = FakeWindowsProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return created_process

    created_coros = []

    def fake_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        terminal_service.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )
    monkeypatch.setattr(terminal_service.asyncio, "create_task", fake_create_task)

    session = _session(command=["cmd"])
    await session._start_windows()
    assert session._process is created_process
    assert len(created_coros) == 2

    session.status = "running"
    await session.write("hello")
    assert created_process.stdin.data == b"hello"

    output: list[tuple[str, bytes]] = []

    async def fake_publish_output(stream: str, chunk: bytes) -> bool:
        output.append((stream, chunk))
        return True

    monkeypatch.setattr(session, "_publish_output", fake_publish_output)
    await session._read_windows_output()
    assert output == [("stdout", b"win-out")]

    exit_events: list[dict[str, object]] = []

    async def fake_publish(event: dict[str, object]) -> None:
        exit_events.append(event)

    async def fake_finalize() -> None:
        session.status = "closed"

    monkeypatch.setattr(session, "_publish", fake_publish)
    monkeypatch.setattr(session, "_finalize_close", fake_finalize)
    session.status = "running"
    await session._wait_for_process()
    assert session.exit_code == 7
    assert exit_events == [{"type": "exit", "exit_code": 7}]

    async def timeout_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(terminal_service.asyncio, "wait_for", timeout_wait_for)
    await session._terminate_process()
    assert created_process.terminated is True
    assert created_process.killed is True


@pytest.mark.anyio
async def test_terminal_posix_start_read_wait_terminate_and_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePosixProcess:
        def __init__(self, *args, **kwargs) -> None:
            self.pid = 4321
            self.wait_calls = 0

        def wait(self) -> int:
            self.wait_calls += 1
            return 3

    import pty

    monkeypatch.setattr(terminal_service.subprocess, "Popen", FakePosixProcess)
    monkeypatch.setattr(terminal_service, "is_windows", lambda: False)
    monkeypatch.setattr(pty, "openpty", lambda: (201, 202))

    closed_fds: list[int] = []
    monkeypatch.setattr(terminal_service.os, "close", lambda fd: closed_fds.append(fd))

    created_coros = []
    original_create_task = asyncio.create_task

    def fake_create_task(coro):
        created_coros.append(coro)
        coro.close()
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(terminal_service.asyncio, "create_task", fake_create_task)

    session = _session()
    await session._start_posix()
    assert session._master_fd == 201
    assert isinstance(session._process, FakePosixProcess)
    assert closed_fds == [202]
    assert len(created_coros) == 2

    reads = iter([b"abc", b""])

    async def fake_to_thread(func, *args):
        if func is terminal_service.os.read:
            return next(reads)
        return func(*args)

    output: list[bytes] = []

    async def fake_publish_output(stream: str, chunk: bytes) -> bool:
        output.append(chunk)
        return True

    monkeypatch.setattr(terminal_service.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(session, "_publish_output", fake_publish_output)
    await session._read_posix_output()
    assert output == [b"abc"]

    exit_events: list[dict[str, object]] = []

    async def fake_publish(event: dict[str, object]) -> None:
        exit_events.append(event)

    async def fake_finalize() -> None:
        session.status = "closed"

    monkeypatch.setattr(session, "_publish", fake_publish)
    monkeypatch.setattr(session, "_finalize_close", fake_finalize)
    session.status = "running"
    await session._wait_for_process()
    assert session.exit_code == 3
    assert exit_events == [{"type": "exit", "exit_code": 3}]

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        terminal_service.os, "killpg", lambda pid, sig: killed.append((pid, sig))
    )

    async def timeout_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(terminal_service.asyncio, "wait_for", timeout_wait_for)
    await session._terminate_process()
    assert killed == [
        (4321, terminal_service.signal.SIGTERM),
        (4321, terminal_service.signal.SIGKILL),
    ]

    task_session = _session()
    task_session.status = "running"
    task_session._master_fd = 303
    task_session._reader_task = original_create_task(asyncio.sleep(10))
    task_session._wait_task = original_create_task(asyncio.sleep(10))
    await task_session._finalize_close()
    assert task_session.status == "closed"
    assert task_session._reader_task is None
    assert task_session._wait_task is None
    assert task_session._master_fd is None


@pytest.mark.anyio
async def test_start_posix_closes_pty_fds_when_spawn_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = terminal_service.TerminalSession(
        session_id="terminal-1",
        cwd="/tmp",
        command=["/bin/sh"],
        env={"TERM": "xterm-256color"},
        created_by="127.0.0.1",
        origin="http://localhost:3000",
        owner_token_hash="token-hash",
    )

    closed_fds: list[int] = []

    monkeypatch.setattr(terminal_service, "is_windows", lambda: False)

    import pty

    monkeypatch.setattr(pty, "openpty", lambda: (101, 102))

    def fake_popen(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        raise OSError("spawn failed")

    monkeypatch.setattr(terminal_service.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(terminal_service.os, "close", lambda fd: closed_fds.append(fd))

    with pytest.raises(OSError, match="spawn failed"):
        await session._start_posix()

    assert closed_fds == [101, 102]
