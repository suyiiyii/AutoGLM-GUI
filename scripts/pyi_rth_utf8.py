"""
PyInstaller Runtime Hook - Force UTF-8 encoding on Windows

This file is executed by PyInstaller BEFORE the main script,
at the earliest possible moment, ensuring UTF-8 encoding is set
before any user code runs.

Reference: https://pyinstaller.org/en/stable/hooks.html#understanding-pyi-rth-hooks
"""

import sys
import os

# Only apply on Windows
if sys.platform == "win32":
    # Set environment variable for any subprocess
    os.environ["PYTHONIOENCODING"] = "utf-8"

    # Reconfigure stdout and stderr to UTF-8
    # This is the official Python 3.7+ way
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    else:
        # Fallback for Python < 3.7 (shouldn't happen with Python 3.11)
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach(), "replace")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach(), "replace")
