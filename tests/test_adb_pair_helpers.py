"""Unit tests for wireless ADB pairing helpers."""

from __future__ import annotations

import subprocess

import pytest

import AutoGLM_GUI.adb_plus.pair as pair


def _completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["adb"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("failed: pairing code was wrong", (False, "Invalid pairing code")),
        (
            "failed: connection refused",
            (
                False,
                "Connection refused - check if wireless debugging is enabled",
            ),
        ),
        ("failed: protocol error", (False, "Pairing failed: failed: protocol error")),
        ("", (False, "Unknown pairing error")),
    ],
)
def test_pair_device_classifies_failure_outputs(
    monkeypatch: pytest.MonkeyPatch, output: str, expected: tuple[bool, str]
) -> None:
    monkeypatch.setattr(
        pair,
        "run_cmd_silently_sync",
        lambda cmd, timeout: _completed(stdout=output),
    )

    assert pair.pair_device("1.2.3.4", 1234, "123456", adb_path="adbx") == expected


def test_pair_device_reports_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("adb failed")

    monkeypatch.setattr(pair, "run_cmd_silently_sync", broken_run)

    assert pair.pair_device("1.2.3.4", 1234, "123456") == (
        False,
        "Pairing error: adb failed",
    )


@pytest.mark.anyio
async def test_pair_device_async_validates_and_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], int]] = []

    async def fake_run(
        cmd: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, timeout))
        return _completed(stdout="success")

    monkeypatch.setattr(pair, "run_cmd_silently", fake_run)

    assert await pair.pair_device_async("1.2.3.4", 1234, "bad") == (
        False,
        "Pairing code must be 6 digits",
    )
    assert await pair.pair_device_async("1.2.3.4", 1234, "123456", "adbx") == (
        True,
        "Successfully paired to 1.2.3.4:1234",
    )
    assert calls == [(["adbx", "pair", "1.2.3.4:1234", "123456"], 30)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "failed: connection refused",
            (
                False,
                "Connection refused - check if wireless debugging is enabled",
            ),
        ),
        ("failed: other", (False, "Pairing failed: failed: other")),
        ("", (False, "Unknown pairing error")),
    ],
)
async def test_pair_device_async_classifies_failures(
    monkeypatch: pytest.MonkeyPatch, output: str, expected: tuple[bool, str]
) -> None:
    async def fake_run(
        cmd: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return _completed(stdout=output)

    monkeypatch.setattr(pair, "run_cmd_silently", fake_run)

    assert await pair.pair_device_async("1.2.3.4", 1234, "123456") == expected


@pytest.mark.anyio
async def test_pair_device_async_reports_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_run(
        cmd: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("async adb failed")

    monkeypatch.setattr(pair, "run_cmd_silently", broken_run)

    assert await pair.pair_device_async("1.2.3.4", 1234, "123456") == (
        False,
        "Pairing error: async adb failed",
    )
