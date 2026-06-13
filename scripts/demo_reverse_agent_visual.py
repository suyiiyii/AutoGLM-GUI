#!/usr/bin/env python3
"""Visual demo for reverse Android Agent integration.

This script produces a screen recording that demonstrates the reverse agent
appearing in the web UI device list and serving screenshots through the
WebSocket command channel.

Prerequisites:
    uv sync
    uv run playwright install chromium
    uv run python scripts/build.py

Usage:
    uv run python scripts/demo_reverse_agent_visual.py

Output:
    docs/assets/reverse_agent_demo.webm
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import multiprocessing
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import websockets
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

BACKEND_PORT = 8765
BASE_URL = f"http://127.0.0.1:{BACKEND_PORT}"
WS_URL = f"ws://127.0.0.1:{BACKEND_PORT}"
OUTPUT_DIR = ROOT / "docs" / "assets"
OUTPUT_PATH = OUTPUT_DIR / "reverse_agent_demo.webm"

# A small red placeholder screenshot returned by the fake Android Agent.
SCREENSHOT_B64: str | None = None


def _make_placeholder_screenshot() -> str:
    img = Image.new("RGB", (360, 640), color=(200, 50, 50))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _poll_backend(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Backend did not become ready in time")


def _wait_for_reverse_agent(agent_id: str, timeout: float = 15.0) -> None:
    synthetic_serial = f"reverse:{agent_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/devices", timeout=2) as resp:
                data = json.loads(resp.read())
                for device in data.get("devices", []):
                    if device.get("serial") == synthetic_serial:
                        return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(
        f"Reverse agent {synthetic_serial} did not appear in device list"
    )


def _start_backend() -> subprocess.Popen:
    env = {"AUTOGLM_TRACE_ENABLED": "0", **dict(subprocess.os.environ)}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "AutoGLM_GUI",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _poll_backend()
    return proc


def _create_pairing() -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE_URL}/api/reverse_agents/pairings",
        data=json.dumps({"display_name": "Demo Android Agent"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _claim_pairing(pairing_code: str) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE_URL}/api/reverse_agents/pairings/claim",
        data=json.dumps(
            {
                "pairing_code": pairing_code,
                "display_name": "Pixel Demo",
                "app_version": "0.3.0",
                "platform": "android",
                "capabilities": [
                    "screenshot",
                    "tap",
                    "swipe",
                    "type_text",
                    "current_app",
                ],
                "metadata": {"model": "Pixel Demo"},
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


async def _fake_agent_session(
    agent_id: str, agent_token: str, screenshot_b64: str
) -> None:
    uri = f"{WS_URL}/api/reverse_agents/agents/{agent_id}/ws?token={agent_token}"
    async with websockets.connect(uri) as ws:
        ready = json.loads(await ws.recv())
        assert ready["type"] == "session_ready"
        heartbeat_interval = ready.get("heartbeat_interval_seconds", 15)

        async def heartbeat_loop() -> None:
            while True:
                await asyncio.sleep(max(heartbeat_interval / 3, 3))
                await ws.send(
                    json.dumps(
                        {
                            "type": "heartbeat",
                            "capabilities": [
                                "screenshot",
                                "tap",
                                "swipe",
                                "type_text",
                                "current_app",
                            ],
                            "metadata": {"model": "Pixel Demo"},
                        }
                    )
                )

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        try:
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.5))
                except asyncio.TimeoutError:
                    continue

                message_type = msg.get("type")
                if message_type == "heartbeat_ack":
                    continue
                if message_type != "command":
                    continue

                command_id = msg["command_id"]
                command_type = msg["command_type"]
                payload = msg.get("payload", {})

                if command_type == "screenshot":
                    result_payload = {
                        "base64_data": screenshot_b64,
                        "width": 360,
                        "height": 640,
                        "is_sensitive": False,
                    }
                elif command_type == "current_app":
                    result_payload = {"app_name": "com.autoglm.demo"}
                elif command_type == "tap":
                    result_payload = {"x": payload.get("x"), "y": payload.get("y")}
                elif command_type == "swipe":
                    result_payload = {"executed": True}
                elif command_type == "type_text":
                    result_payload = {"text": payload.get("text")}
                else:
                    result_payload = {"error": "unsupported command"}

                await ws.send(
                    json.dumps(
                        {
                            "type": "command_result",
                            "command_id": command_id,
                            "success": True,
                            "payload": result_payload,
                        }
                    )
                )
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass


def _run_fake_agent_process(
    agent_id: str, agent_token: str, screenshot_b64: str
) -> None:
    asyncio.run(_fake_agent_session(agent_id, agent_token, screenshot_b64))


def _start_fake_agent(
    agent_id: str, agent_token: str, screenshot_b64: str
) -> multiprocessing.Process:
    proc = multiprocessing.Process(
        target=_run_fake_agent_process,
        args=(agent_id, agent_token, screenshot_b64),
        daemon=True,
    )
    proc.start()
    return proc


def _record_demo() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    debug_screenshot = OUTPUT_DIR / "reverse_agent_demo_debug.png"
    if debug_screenshot.exists():
        debug_screenshot.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(OUTPUT_DIR),
            record_video_size={"width": 1600, "height": 900},
        )
        page = context.new_page()
        page.on("console", lambda msg: print(f"[console {msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: print(f"[pageerror] {exc}"))
        try:
            page.goto(f"{BASE_URL}/")
            page.wait_for_load_state("load")

            # Wait for the reverse agent to appear in the device list.
            page.wait_for_selector("text=Android Agent", timeout=20000)
            page.wait_for_timeout(1000)

            # The device is auto-selected. Wait for the screenshot to appear.
            page.wait_for_selector("img[alt='Device Screenshot']", timeout=20000)
            page.wait_for_timeout(3000)
        except Exception:
            page.screenshot(path=str(debug_screenshot), full_page=True)
            html_path = OUTPUT_DIR / "reverse_agent_demo_debug.html"
            html_path.write_text(page.content(), encoding="utf-8")
            raise
        finally:
            context.close()
            browser.close()

        # Playwright saves the video with a random name; rename it.
        video_files = sorted(
            OUTPUT_DIR.glob("*.webm"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if video_files:
            video_files[0].rename(OUTPUT_PATH)
            print(f"Demo video saved to: {OUTPUT_PATH}")
        else:
            print("No video file was produced.")


def main() -> int:
    global SCREENSHOT_B64
    SCREENSHOT_B64 = _make_placeholder_screenshot()

    backend_proc: subprocess.Popen | None = None
    agent_proc: multiprocessing.Process | None = None

    try:
        print("Starting backend...")
        backend_proc = _start_backend()

        print("Creating reverse agent pairing...")
        pairing = _create_pairing()
        claim = _claim_pairing(pairing["pairing_code"])
        agent_id = claim["agent_id"]
        agent_token = claim["agent_token"]

        print("Starting fake Android Agent...")
        agent_proc = _start_fake_agent(agent_id, agent_token, SCREENSHOT_B64)

        # Wait until the reverse agent appears in the device list.
        print("Waiting for reverse agent to register...")
        _wait_for_reverse_agent(agent_id, timeout=15)

        print("Recording demo with Playwright...")
        _record_demo()
        return 0
    except Exception as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if agent_proc is not None:
            agent_proc.terminate()
            agent_proc.join(timeout=5)
        if backend_proc is not None:
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
