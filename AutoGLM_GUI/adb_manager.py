"""ADB binary detection and auto-download."""

import io
import platform
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path

_CACHE_DIR = Path.home() / ".cache" / "autoglm"
_PLATFORM_TOOLS_DIR = _CACHE_DIR / "platform-tools"

_PLATFORM_MAP = {
    "linux": "linux",
    "darwin": "darwin",
    "windows": "windows",
}

_ADB_BINARY = "adb.exe" if platform.system().lower() == "windows" else "adb"


def _platform_name() -> str:
    system = platform.system().lower()
    name = _PLATFORM_MAP.get(system)
    if name is None:
        raise RuntimeError(
            f"Unsupported platform: {system}. Please install ADB manually."
        )
    return name


def ensure_adb() -> str:
    """Return a usable ADB binary path, downloading if necessary.

    Priority:
    1. System PATH
    2. ~/.cache/autoglm/platform-tools/adb  (previously downloaded)
    3. Download from Google and cache

    Returns:
        Absolute path string to the ADB binary.

    Raises:
        RuntimeError: If ADB cannot be found or downloaded.
    """
    # 1. System PATH
    system_adb = shutil.which("adb")
    if system_adb:
        return system_adb

    print("[AutoGLM] ADB not found in system PATH.")

    # 2. Cached download
    cached_adb = _PLATFORM_TOOLS_DIR / _ADB_BINARY
    if cached_adb.exists():
        print(f"[AutoGLM] ADB ready: {cached_adb}")
        return str(cached_adb)

    # 3. Download
    platform_name = _platform_name()
    url = f"https://dl.google.com/android/repository/platform-tools-latest-{platform_name}.zip"
    print("[AutoGLM] Downloading Android Platform Tools from Google (~12MB)...")

    try:
        data = _download_with_progress(url)
    except Exception as e:
        raise RuntimeError(
            f"Failed to download Android Platform Tools: {e}\n"
            "Please install ADB manually: https://developer.android.com/tools/adb"
        ) from e

    print("[AutoGLM] Extracting...")
    try:
        _PLATFORM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.infolist():
                # Strip the leading "platform-tools/" prefix so files land
                # directly in _PLATFORM_TOOLS_DIR.
                rel = Path(member.filename)
                parts = rel.parts
                if len(parts) < 2:
                    continue
                dest = _PLATFORM_TOOLS_DIR / Path(*parts[1:])
                if member.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(member.filename))
    except Exception as e:
        raise RuntimeError(f"Failed to extract platform-tools: {e}") from e

    if not cached_adb.exists():
        raise RuntimeError(
            f"ADB binary not found after extraction (expected: {cached_adb}).\n"
            "Please install ADB manually: https://developer.android.com/tools/adb"
        )

    # Make executable on Unix
    if platform.system().lower() != "windows":
        cached_adb.chmod(
            cached_adb.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )

    print(f"[AutoGLM] ADB ready: {cached_adb}")
    return str(cached_adb)


def _download_with_progress(url: str) -> bytes:
    """Download *url* and return raw bytes, printing a simple progress indicator."""
    downloaded = 0

    def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
        nonlocal downloaded
        downloaded = min(
            block_num * block_size,
            total_size if total_size > 0 else block_num * block_size,
        )
        if total_size > 0:
            pct = downloaded * 100 // total_size
            print(
                f"\r[AutoGLM] Downloading... {pct}% ({downloaded // 1024 // 1024}MB / {total_size // 1024 // 1024}MB)",
                end="",
                flush=True,
            )

    import tempfile
    import os

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        tmp_path = tmp.name

    try:
        urllib.request.urlretrieve(url, tmp_path, reporthook=_reporthook)
        print()  # newline after progress
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
