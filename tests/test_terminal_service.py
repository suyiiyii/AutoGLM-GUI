"""Unit tests for terminal session defaults."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

import AutoGLM_GUI.adb_terminal_service as terminal_service


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
async def test_terminal_output_limit_triggers_close() -> None:
    session = terminal_service.TerminalSession(
        session_id="terminal-1",
        cwd="/tmp",
        command=["/bin/sh"],
        env={"TERM": "xterm-256color"},
        created_by="127.0.0.1",
        origin="http://localhost:3000",
        owner_token_hash="token-hash",
        max_output_bytes=4,
    )

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
    session = terminal_service.TerminalSession(
        session_id="terminal-1",
        cwd="/tmp",
        command=["/bin/sh"],
        env={"TERM": "xterm-256color"},
        created_by="127.0.0.1",
        origin="http://localhost:3000",
        owner_token_hash="token-hash",
        buffer_size=2,
        max_buffer_bytes=4096,
    )

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
