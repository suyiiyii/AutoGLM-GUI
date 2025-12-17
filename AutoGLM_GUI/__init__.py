"""AutoGLM-GUI package metadata."""

import subprocess
import sys
from functools import wraps
from importlib import metadata

# 修复 Windows 编码问题 - 必须在所有其他导入之前
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


# ============================================================================
# Fix Windows encoding issue: Force UTF-8 for all subprocess calls
# ============================================================================
# On Windows, subprocess defaults to GBK encoding which fails when ADB/scrcpy
# output UTF-8 characters. This monkey patch ensures all subprocess calls
# use UTF-8 encoding by default.

_original_run = subprocess.run
_original_popen = subprocess.Popen


@wraps(_original_run)
def _patched_run(*args, **kwargs):
    """Patched subprocess.run that defaults to UTF-8 encoding on Windows."""
    if sys.platform == "win32":
        # Add encoding='utf-8' if text=True is set but encoding is not specified
        if kwargs.get("text") or kwargs.get("universal_newlines"):
            if "encoding" not in kwargs:
                kwargs["encoding"] = "utf-8"
    return _original_run(*args, **kwargs)


class _PatchedPopen(_original_popen):
    """Patched subprocess.Popen that defaults to UTF-8 encoding on Windows."""

    def __init__(self, *args, **kwargs):
        if sys.platform == "win32":
            # Add encoding='utf-8' if text=True is set but encoding is not specified
            if kwargs.get("text") or kwargs.get("universal_newlines"):
                if "encoding" not in kwargs:
                    kwargs["encoding"] = "utf-8"
        super().__init__(*args, **kwargs)


# Apply the patches globally
subprocess.run = _patched_run
subprocess.Popen = _PatchedPopen

# ============================================================================

# Expose package version at runtime; fall back to "unknown" during editable/dev runs
try:
    __version__ = metadata.version("autoglm-gui")
except metadata.PackageNotFoundError:
    __version__ = "unknown"
