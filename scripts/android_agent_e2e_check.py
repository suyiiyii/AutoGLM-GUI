#!/usr/bin/env python3
"""End-to-end check for the reverse Android Agent against a live emulator.

This script assumes:
  * an Android device/emulator is connected and visible to ``adb``;
  * the AutoGLM-GUI backend is already running and reachable at ``BASE_URL``;
  * the Android Agent debug APK is installed (package ``com.autoglm.agent``).

It drives the whole reverse-agent path the way CI would, with no fragile UI
tapping for setup:

  1. enable the accessibility service via secure settings;
  2. pre-grant MediaProjection via ``appops`` (avoids the consent dialog);
  3. create a pairing through the real REST API;
  4. launch the app with debug intent extras so it auto-claims the pairing and
     requests screen capture;
  5. wait for the reverse agent to register as a device;
  6. assert real device effects through the reverse command channel:
     - ``screenshot`` returns a real image (not a solid placeholder),
     - ``current_app`` returns the agent package,
     - ``tap`` actually lands on screen (the developer toggle flips its label).

On failure it dumps logcat and a screenshot into ``ARTIFACT_DIR`` and exits 1.

Env vars:
  BASE_URL        backend base url as seen from this host (default http://127.0.0.1:8080)
  DEVICE_BASE_URL backend base url as seen from the device (default http://10.0.2.2:8080)
  ARTIFACT_DIR    where to write failure artifacts (default /tmp/android-agent-e2e)
  ADB             adb binary (default "adb")
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

PACKAGE = "com.autoglm.agent"
ACTIVITY = f"{PACKAGE}/.MainActivity"
A11Y_SERVICE = f"{PACKAGE}/{PACKAGE}.service.DeviceAccessibilityService"

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
DEVICE_BASE_URL = os.environ.get("DEVICE_BASE_URL", "http://10.0.2.2:8080").rstrip("/")
ARTIFACT_DIR = os.environ.get("ARTIFACT_DIR", "/tmp/android-agent-e2e")
ADB = os.environ.get("ADB", "adb")


def adb(*args: str, check: bool = True) -> str:
    result = subprocess.run([ADB, *args], capture_output=True, text=True, timeout=120)
    if check and result.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def api_post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as resp:
        return json.loads(resp.read())


def send_command(agent_id: str, command_type: str, payload: dict | None = None) -> dict:
    return api_post(
        f"/api/reverse_agents/agents/{agent_id}/commands",
        {"command_type": command_type, "payload": payload or {}},
    )


def enable_accessibility() -> None:
    adb("shell", "settings", "put", "secure", "enabled_accessibility_services", A11Y_SERVICE)
    adb("shell", "settings", "put", "secure", "accessibility_enabled", "1")


def kick_accessibility() -> None:
    """Force the framework to rebind the a11y service.

    Setting the secure value before the app has ever run does not reliably bind
    the service (the framework won't bind a never-launched app), and re-writing
    the same value is a no-op. Toggling accessibility_enabled 0 -> 1 forces a
    re-evaluation once the app process is alive.
    """
    adb("shell", "settings", "put", "secure", "accessibility_enabled", "0")
    adb("shell", "settings", "put", "secure", "enabled_accessibility_services", A11Y_SERVICE)
    adb("shell", "settings", "put", "secure", "accessibility_enabled", "1")


def ui_dump() -> str:
    adb("shell", "uiautomator", "dump", "/sdcard/e2e_ui.xml")
    return adb("shell", "cat", "/sdcard/e2e_ui.xml")


def find_node(xml: str, resource_id: str) -> tuple[int, int, str] | None:
    """Return (center_x, center_y, text) for the first node with resource_id."""
    # Match negative coordinates too: scroll-view children that are scrolled
    # above the viewport report negative bounds, and scroll_to needs to see them
    # to know it has overshot and should scroll back down.
    pattern = re.compile(r'<node([^>]*?)bounds="\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"')
    for m in pattern.finditer(xml):
        attrs = m.group(1)
        rid = re.search(r'resource-id="([^"]*)"', attrs)
        if not rid or not rid.group(1).endswith(resource_id):
            continue
        text = re.search(r'text="([^"]*)"', attrs)
        x = (int(m.group(2)) + int(m.group(4))) // 2
        y = (int(m.group(3)) + int(m.group(5))) // 2
        return x, y, (text.group(1) if text else "")
    return None


def screen_size() -> tuple[int, int]:
    """Return the effective (width, height) in px.

    `wm size` may print both a "Physical size" and an "Override size" (when a
    test sets one); the override is what's actually rendered, so prefer it.
    """
    out = adb("shell", "wm", "size", check=False)
    m = (
        re.search(r"Override size:\s*(\d+)x(\d+)", out)
        or re.search(r"Physical size:\s*(\d+)x(\d+)", out)
        or re.search(r"(\d+)x(\d+)", out)
    )
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)


def scroll_to(resource_id: str, max_swipes: int = 16) -> tuple[int, int, str]:
    """Scroll until a node with resource_id sits in the tappable safe band.

    `uiautomator dump` reports scroll-view children even when they are off the
    visible viewport (negative or beyond-height bounds), so we must check the
    node's on-screen position, not just its presence. We accept it only when its
    center is within [12%, 82%] of screen height (clear of the app bar and the
    bottom navigation), nudging up or down as needed. Coordinates are derived
    from the real screen size — CI emulators run at 320x640.
    """
    w, h = screen_size()
    cx = w // 2
    # Acceptable tap band: below the app bar, above the bottom nav. The
    # developer toggle is the last element, so when the scroll bottoms out it
    # settles low (center ~0.90h on 320x640) — keep the lower bound generous.
    top, bottom = 0.07 * h, 0.93 * h
    for _ in range(max_swipes):
        node = find_node(ui_dump(), resource_id)
        if node:
            cy = node[1]
            if top <= cy <= bottom:
                return node
            if cy > bottom:  # below the band -> scroll content up
                adb("shell", "input", "swipe", str(cx), str(int(h * 0.7)), str(cx), str(int(h * 0.4)), "300")
            else:  # above the band -> scroll content down
                adb("shell", "input", "swipe", str(cx), str(int(h * 0.4)), str(cx), str(int(h * 0.7)), "300")
        else:  # not in the tree yet -> large swipe up to reveal lower content
            adb("shell", "input", "swipe", str(cx), str(int(h * 0.8)), str(cx), str(int(h * 0.25)), "300")
        time.sleep(1)
    raise AssertionError(f"could not bring node {resource_id} into the tappable area")


def dump_artifacts(tag: str) -> None:
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    try:
        png = subprocess.run(
            [ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=60
        ).stdout
        with open(os.path.join(ARTIFACT_DIR, f"{tag}.png"), "wb") as f:
            f.write(png)
    except Exception as exc:  # noqa: BLE001
        print(f"  (screenshot capture failed: {exc})")
    try:
        log = adb("logcat", "-d", "-t", "400", check=False)
        with open(os.path.join(ARTIFACT_DIR, f"{tag}.logcat.txt"), "w") as f:
            f.write(log)
    except Exception as exc:  # noqa: BLE001
        print(f"  (logcat capture failed: {exc})")


def distinct_colors(png_bytes: bytes) -> int:
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    colors = img.getcolors(maxcolors=1_000_000)
    return len(colors) if colors else 1_000_001


def main() -> int:
    print(f"BASE_URL={BASE_URL}  DEVICE_BASE_URL={DEVICE_BASE_URL}")

    # 0. sanity: device + backend reachable
    devices = adb("devices").strip().splitlines()[1:]
    online = [d for d in devices if d.strip().endswith("device")]
    assert online, f"no online adb device: {devices}"
    print(f"adb device: {online[0].split()[0]}")
    assert api_get("/api/health"), "backend /api/health not OK"

    # 1. deterministic permission setup (no UI tapping).
    # MediaProjection is pre-granted now; accessibility is enabled AFTER the app
    # launches (step 3.5) because the framework won't bind an a11y service for an
    # app that has never run.
    adb("shell", "appops", "set", PACKAGE, "PROJECT_MEDIA", "allow")
    enable_accessibility()
    print("MediaProjection pre-granted via appops; accessibility set")

    # 2. real pairing
    pairing = api_post("/api/reverse_agents/pairings", {})
    code = pairing["pairing_code"]
    print(f"pairing code: {code}")

    # 3. launch app with debug injection extras (auto-claim + request capture).
    # Note: we deliberately do NOT force-stop the app, because that also kills
    # the accessibility service and delays its rebind. onNewIntent handles the
    # injection if the app is already running.
    adb(
        "shell",
        "am",
        "start",
        "-n",
        ACTIVITY,
        "--ez",
        "request_capture",
        "true",
        "--es",
        "test_server_url",
        DEVICE_BASE_URL,
        "--es",
        "test_pairing_code",
        code,
    )

    # 3.5. now that the app process is alive, force the a11y service to bind.
    time.sleep(2)
    kick_accessibility()

    # 4. wait for the reverse agent to register as a device
    agent_id = None
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        for dev in api_get("/api/devices").get("devices", []):
            serial = dev.get("serial", "")
            if serial.startswith("reverse:"):
                agent_id = serial.split("reverse:", 1)[1]
                break
        if agent_id:
            break
        time.sleep(2)
    assert agent_id, "reverse agent never registered as a device"
    print(f"reverse agent registered: {agent_id}")

    # 4b. wait until the websocket session is actually connected (not stale/offline)
    status = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        info = api_get(f"/api/reverse_agents/registry/{agent_id}")
        status = info.get("connection_status")
        if status == "connected":
            break
        time.sleep(2)
    assert status == "connected", f"agent never reached connected state (last={status})"
    print(f"connection status: {status}")

    # 5a. screenshot must be a real image, not a solid placeholder.
    # Retry: the MediaProjection grant (appops-approved consent activity)
    # completes a moment after the websocket connects, so the first screenshot
    # can race ahead of "Screen capture permission has not been granted".
    shot = None
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        shot = send_command(agent_id, "screenshot")
        if str(shot.get("success")).lower() == "true":
            break
        time.sleep(2)
    assert str(shot.get("success")).lower() == "true", f"screenshot failed: {shot}"
    payload = shot["payload"]
    png = base64.b64decode(payload["base64_data"])
    colors = distinct_colors(png)
    assert payload["width"] > 0 and payload["height"] > 0, payload
    assert colors > 100, f"screenshot looks like a placeholder ({colors} colors)"
    print(
        f"screenshot OK: {payload['width']}x{payload['height']}, {colors} colors, {len(png)} bytes"
    )

    # 5b. current_app — also serves as an accessibility-service readiness gate
    # (current_app / tap need the a11y service bound, which can lag the launch).
    cur = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        cur = send_command(agent_id, "current_app")
        if str(cur.get("success")).lower() == "true":
            break
        # a11y service may still be binding; re-toggle to force it and retry
        kick_accessibility()
        time.sleep(3)
    assert str(cur.get("success")).lower() == "true", f"current_app failed: {cur}"
    assert cur["payload"]["app_name"] == PACKAGE, cur
    print(f"current_app OK: {cur['payload']['app_name']}")

    # 5c. tap must land on screen: tapping the developer toggle flips its label
    x, y, before = scroll_to("developerToggleButton")
    tap = send_command(agent_id, "tap", {"x": x, "y": y})
    assert str(tap.get("success")).lower() == "true", f"tap command failed: {tap}"
    time.sleep(1.5)
    after = find_node(ui_dump(), "developerToggleButton")[2]
    assert after != before, f"tap had no on-screen effect (label stayed {before!r})"
    print(f"tap OK: developer toggle label changed {before!r} -> {after!r}")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"\nE2E CHECK FAILED: {exc}", file=sys.stderr)
        dump_artifacts("failure")
        sys.exit(1)
