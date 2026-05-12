"""
PyInstaller Runtime Hook - Force UTF-8 encoding for stdout/stderr

This file is executed by PyInstaller BEFORE the main script,
at the earliest possible moment, ensuring UTF-8 encoding is set
for I/O streams.

IMPORTANT: UTF-8 mode is enabled via build-time OPTIONS in autoglm.spec:
    [('X utf8_mode=1', None, 'OPTION')]

This hook only handles stdout/stderr reconfiguration for extra safety.

Reference:
- https://pyinstaller.org/en/stable/hooks.html#understanding-pyi-rth-hooks
- https://github.com/pyinstaller/pyinstaller/discussions/9065
"""

import os
import sys

# Only apply on Windows
if sys.platform == "win32":
    # NOTE: PYTHONUTF8 environment variable is INEFFECTIVE for PyInstaller 6.9+
    # UTF-8 mode is now controlled by build-time OPTIONS in spec file
    # See: https://github.com/pyinstaller/pyinstaller/discussions/9065

    # Set for any subprocess spawned by the application
    os.environ["PYTHONIOENCODING"] = "utf-8"

    # Reconfigure stdout and stderr to UTF-8
    # This is additional safety for console output
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    else:
        # Fallback for Python < 3.7 (shouldn't happen with Python 3.11)
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach(), "replace")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach(), "replace")
