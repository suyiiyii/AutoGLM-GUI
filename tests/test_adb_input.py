"""Unit tests for ADB text input helpers."""

from __future__ import annotations

import subprocess

import pytest

import AutoGLM_GUI.adb.input as adb_input


def test_type_text_empty_string_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(adb_input.subprocess, "run", fake_run)

    adb_input.type_text("", device_id="device-1")

    assert calls == []


def test_type_text_non_empty_string_broadcasts_base64(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(adb_input.subprocess, "run", fake_run)

    adb_input.type_text("123", device_id="device-1")

    assert calls == [
        (
            [
                "adb",
                "-s",
                "device-1",
                "shell",
                "am",
                "broadcast",
                "-a",
                "ADB_INPUT_B64",
                "--es",
                "msg",
                "MTIz",
            ],
            {"capture_output": True, "text": True, "check": True},
        )
    ]


def test_detect_and_set_adb_keyboard_does_not_broadcast_empty_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[-4:] == ["settings", "get", "secure", "default_input_method"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="com.android.adbkeyboard/.AdbIME\n", stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(adb_input.subprocess, "run", fake_run)

    original_ime = adb_input.detect_and_set_adb_keyboard(device_id="device-1")

    assert original_ime == "com.android.adbkeyboard/.AdbIME"
    assert calls == [
        [
            "adb",
            "-s",
            "device-1",
            "shell",
            "settings",
            "get",
            "secure",
            "default_input_method",
        ]
    ]
