"""ADB IP helpers (prefer WiFi address, skip cellular interfaces)."""

from __future__ import annotations

import re
import subprocess
from typing import Optional

__all__ = ["get_wifi_ip"]


def _run(adb_path: str, device_id: Optional[str], cmd: list[str]) -> str:
    base_cmd = [adb_path]
    if device_id:
        base_cmd.extend(["-s", device_id])
    result = subprocess.run(
        base_cmd + ["shell", *cmd], capture_output=True, text=True, timeout=5
    )
    return (result.stdout or "") + (result.stderr or "")


def _extract_ip(text: str) -> Optional[str]:
    m = re.search(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", text)
    if not m:
        return None
    ip = m.group(0)
    if ip == "0.0.0.0":
        return None
    return ip


def get_wifi_ip(
    adb_path: str = "adb", device_id: Optional[str] = None
) -> Optional[str]:
    """
    Prefer WiFi IP when multiple interfaces exist.

    - First try `ip -4 route get 8.8.8.8`, skip typical cellular interfaces (ccmni/rmnet).
    - Fallback to `ip -4 addr show wlan0`.
    Returns None if no suitable IP is found or on error.
    """
    # 1) route
    try:
        route_out = _run(adb_path, device_id, ["ip", "-4", "route", "get", "8.8.8.8"])
        for line in route_out.splitlines():
            if "src" not in line:
                continue
            parts = line.split()
            iface = None
            ip = None
            if "dev" in parts:
                try:
                    iface = parts[parts.index("dev") + 1]
                except Exception:
                    pass
            if "src" in parts:
                try:
                    ip = parts[parts.index("src") + 1]
                except Exception:
                    pass
            if not ip or ip == "0.0.0.0":
                continue
            if iface and (iface.startswith("ccmni") or iface.startswith("rmnet")):
                continue
            return ip
    except Exception:
        pass

    # 2) wlan0 addr
    try:
        addr_out = _run(adb_path, device_id, ["ip", "-4", "addr", "show", "wlan0"])
        ip = _extract_ip(addr_out)
        if ip:
            return ip
    except Exception:
        pass

    return None
