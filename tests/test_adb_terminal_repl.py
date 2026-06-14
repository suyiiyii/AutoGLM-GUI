"""Unit tests for the ADB-only web terminal REPL."""

from __future__ import annotations

import subprocess

import pytest

import AutoGLM_GUI.adb_terminal_repl as repl


def test_resolve_adb_binary_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOGLM_ADB_PATH", raising=False)
    assert repl._resolve_adb_binary() == "adb"

    monkeypatch.setenv("AUTOGLM_ADB_PATH", "/opt/android/adb")
    assert repl._resolve_adb_binary() == "/opt/android/adb"


def test_handle_builtin_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert repl._handle_builtin("help") is True
    assert "AutoGLM Web Terminal" in capsys.readouterr().out

    assert repl._handle_builtin("?") is True
    assert "Allowed commands" in capsys.readouterr().out

    assert repl._handle_builtin("clear") is True
    assert "\033[2J\033[H" in capsys.readouterr().out

    assert repl._handle_builtin("adb") is False

    with pytest.raises(EOFError):
        repl._handle_builtin("exit")
    with pytest.raises(EOFError):
        repl._handle_builtin("quit")


def test_run_adb_command_parsing_and_validation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repl._run_adb_command("adb shell 'unterminated")
    assert "Parse error:" in capsys.readouterr().out

    repl._run_adb_command("")
    assert capsys.readouterr().out == ""

    repl._run_adb_command("help")
    assert "Built-ins:" in capsys.readouterr().out

    repl._run_adb_command("ls")
    assert "Only adb commands are allowed." in capsys.readouterr().out


def test_run_adb_command_invokes_resolved_adb_binary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert check is False
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setenv("AUTOGLM_ADB_PATH", "/custom/adb")
    monkeypatch.setattr(repl.subprocess, "run", fake_run)

    repl._run_adb_command("adb devices")

    assert calls == [["/custom/adb", "devices"]]
    assert capsys.readouterr().out == ""


def test_run_adb_command_reports_process_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        repl.subprocess,
        "run",
        lambda args, check: subprocess.CompletedProcess(args=args, returncode=42),
    )

    repl._run_adb_command("adb shell true")

    assert "[exit code 42]" in capsys.readouterr().out


def test_run_adb_command_handles_missing_adb_and_interrupts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing_adb(args: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setenv("AUTOGLM_ADB_PATH", "/missing/adb")
    monkeypatch.setattr(repl.subprocess, "run", missing_adb)
    repl._run_adb_command("adb devices")
    assert "ADB binary not found: /missing/adb" in capsys.readouterr().out

    def interrupted(args: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        raise KeyboardInterrupt

    monkeypatch.setattr(repl.subprocess, "run", interrupted)
    repl._run_adb_command("adb devices")
    assert "^C" in capsys.readouterr().out


def test_main_handles_input_interrupts_and_eof(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = iter([KeyboardInterrupt, "", "adb devices", EOFError])
    commands: list[str] = []

    def fake_input(prompt: str) -> str:
        next_value = next(inputs)
        if isinstance(next_value, type) and issubclass(next_value, BaseException):
            raise next_value
        return next_value

    def fake_run_adb_command(line: str) -> None:
        commands.append(line)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(repl, "_run_adb_command", fake_run_adb_command)

    assert repl.main() == 0
    assert commands == ["adb devices"]
    assert "^C" in capsys.readouterr().out


def test_main_returns_on_exit_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: "exit")

    assert repl.main() == 0
