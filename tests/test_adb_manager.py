"""Unit tests for ADB binary discovery and download helpers."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest

import AutoGLM_GUI.adb_manager as adb_manager


def test_platform_name_rejects_unsupported_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adb_manager.platform, "system", lambda: "Plan9")

    with pytest.raises(RuntimeError, match="Unsupported platform: plan9"):
        adb_manager._platform_name()


def test_ensure_adb_reports_extract_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform_tools = tmp_path / "platform-tools"
    monkeypatch.setattr(adb_manager.shutil, "which", lambda name: None)
    monkeypatch.setattr(adb_manager, "_PLATFORM_TOOLS_DIR", platform_tools)
    monkeypatch.setattr(adb_manager, "_ADB_BINARY", "adb")
    monkeypatch.setattr(adb_manager, "_platform_name", lambda: "linux")
    monkeypatch.setattr(adb_manager, "_download_with_progress", lambda url: b"not zip")

    with pytest.raises(RuntimeError, match="Failed to extract platform-tools"):
        adb_manager.ensure_adb()


def test_ensure_adb_reports_missing_binary_after_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform_tools = tmp_path / "platform-tools"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("platform-tools/readme.txt", "missing adb")

    monkeypatch.setattr(adb_manager.shutil, "which", lambda name: None)
    monkeypatch.setattr(adb_manager, "_PLATFORM_TOOLS_DIR", platform_tools)
    monkeypatch.setattr(adb_manager, "_ADB_BINARY", "adb")
    monkeypatch.setattr(adb_manager, "_platform_name", lambda: "linux")
    monkeypatch.setattr(
        adb_manager, "_download_with_progress", lambda url: data.getvalue()
    )

    with pytest.raises(RuntimeError, match="ADB binary not found after extraction"):
        adb_manager.ensure_adb()


def test_ensure_adb_extracts_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform_tools = tmp_path / "platform-tools"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("platform-tools/tools/", "")
        zf.writestr("platform-tools/tools/adb", "adb")

    monkeypatch.setattr(adb_manager.shutil, "which", lambda name: None)
    monkeypatch.setattr(adb_manager, "_PLATFORM_TOOLS_DIR", platform_tools)
    monkeypatch.setattr(adb_manager, "_ADB_BINARY", "tools/adb")
    monkeypatch.setattr(adb_manager, "_platform_name", lambda: "linux")
    monkeypatch.setattr(
        adb_manager, "_download_with_progress", lambda url: data.getvalue()
    )

    assert adb_manager.ensure_adb() == str(platform_tools / "tools" / "adb")


def test_download_with_progress_reads_tempfile_and_ignores_unlink_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_urlretrieve(url: str, filename: str, reporthook) -> None:
        Path(filename).write_bytes(b"zip-bytes")
        reporthook(1, 4, 8)
        reporthook(2, 4, 8)

    monkeypatch.setattr(adb_manager.urllib.request, "urlretrieve", fake_urlretrieve)
    monkeypatch.setattr(os, "unlink", lambda path: (_ for _ in ()).throw(OSError))

    assert (
        adb_manager._download_with_progress("https://example.com/tools.zip")
        == b"zip-bytes"
    )
    assert "Downloading... 100%" in capsys.readouterr().out
