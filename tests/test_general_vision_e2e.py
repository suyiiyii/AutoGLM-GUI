"""E2E test for the general vision agent with real API + mock device.

Tests the full pipeline:
  Mock Device → AsyncGeneralVisionAgent → Real Gemini API → Function Calling → Action Execution

Records timing for each phase.
"""

import asyncio
import base64
import io
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest
from PIL import Image

from AutoGLM_GUI.agents.general_vision.async_agent import AsyncGeneralVisionAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import Screenshot


@dataclass
class TimingRecord:
    phase: str
    duration_ms: float


class TimingTracker:
    def __init__(self):
        self.records: list[TimingRecord] = []
        self._start: float = 0

    def start(self, phase: str):
        self._phase = phase
        self._start = time.perf_counter()

    def stop(self):
        elapsed = (time.perf_counter() - self._start) * 1000
        self.records.append(TimingRecord(self._phase, elapsed))
        return elapsed

    def summary(self) -> str:
        lines = ["\n===== E2E Timing Summary ====="]
        total = 0.0
        for r in self.records:
            lines.append(f"  {r.phase:<30s} {r.duration_ms:>8.1f} ms")
            total += r.duration_ms
        lines.append(f"  {'TOTAL':<30s} {total:>8.1f} ms")
        lines.append("=" * 38)
        return "\n".join(lines)


def create_mock_device() -> MagicMock:
    """Create a mock device that returns a fake Android home screen screenshot."""
    device = MagicMock()
    device.device_id = "mock-e2e-001"

    img = Image.new("RGB", (1080, 2400), color=(30, 30, 30))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    colors = [(66, 133, 244), (52, 168, 83), (234, 67, 53), (251, 188, 4)]
    for i, color in enumerate(colors):
        x = 100 + i * 250
        draw.rectangle([x, 1800, x + 180, 1980], fill=color)
    draw.rectangle([100, 1400, 280, 1580], fill=(7, 193, 96))
    draw.text((120, 1590), "WeChat", fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    device.get_screenshot.return_value = Screenshot(
        base64_data=img_b64, width=1080, height=2400
    )
    device.get_current_app.return_value = "System Home"
    device.tap.return_value = None
    device.swipe.return_value = None
    device.type_text.return_value = None
    device.back.return_value = None
    device.home.return_value = None
    device.launch_app.return_value = True
    device.long_press.return_value = None
    device.double_tap.return_value = None
    device.clear_text.return_value = None
    device.detect_and_set_adb_keyboard.return_value = (
        "com.android.inputmethod.latin/.LatinIME"
    )
    device.restore_keyboard.return_value = None

    return device


async def run_e2e_test():
    tracker = TimingTracker()

    tracker.start("1. Create mock device")
    device = create_mock_device()
    tracker.stop()

    tracker.start("2. Create agent")
    model_config = ModelConfig(
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.environ.get("OPENAI_API_KEY", "test-key"),
        model_name="gemini-3.1-pro-preview",
        max_tokens=1000,
        temperature=0.0,
    )
    agent_config = AgentConfig(
        max_steps=5,
        lang="cn",
        verbose=True,
    )
    agent = AsyncGeneralVisionAgent(
        model_config=model_config,
        agent_config=agent_config,
        device=device,
    )
    tracker.stop()

    task = "打开微信"
    print(f"\n📱 Task: {task}")
    print("-" * 50)

    events: list[dict[str, Any]] = []
    step_count = 0

    tracker.start("3. Full stream execution")
    stream_start = time.perf_counter()

    async for event in agent.stream(task):
        event_type = event["type"]
        event_data = event["data"]

        if event_type == "thinking":
            chunk = event_data.get("chunk", "")
            if chunk.strip():
                print(f"  💭 Thinking: {chunk[:100]}...")

        elif event_type == "step":
            step_count += 1
            step_time = (time.perf_counter() - stream_start) * 1000
            action = event_data.get("action")
            action_dict = action if isinstance(action, dict) else {}
            action_name = action_dict.get("action", action_dict.get("_metadata", "?"))
            print(f"  Step {step_count}: {action_name} (cumulative: {step_time:.0f}ms)")
            print(f"    Action: {json.dumps(action_dict, ensure_ascii=False)}")
            print(f"    Success: {event_data.get('success')}")

            if event_data.get("finished"):
                print(f"  ✅ Finished: {event_data.get('message')}")

        elif event_type == "done":
            print(f"\n  🏁 Done: {event_data.get('message')}")
            print(
                f"     Steps: {event_data.get('steps')}, Success: {event_data.get('success')}"
            )

        elif event_type == "error":
            print(f"  ❌ Error: {event_data.get('message')}")

        events.append(event)

    tracker.stop()

    tracker.start("4. Verify results")

    event_types = [e["type"] for e in events]
    has_step = "step" in event_types
    has_done = "done" in event_types

    print(f"\n📊 Event types: {event_types}")
    print(f"   Has step: {has_step}")
    print(f"   Has done: {has_done}")
    print(f"   Total events: {len(events)}")

    device_calls = []
    if device.tap.called:
        device_calls.append(f"tap({device.tap.call_args})")
    if device.launch_app.called:
        device_calls.append(f"launch_app({device.launch_app.call_args})")
    if device.swipe.called:
        device_calls.append(f"swipe({device.swipe.call_args})")
    if device.back.called:
        device_calls.append("back()")
    if device.home.called:
        device_calls.append("home()")

    print(f"   Device calls: {device_calls or ['none (finish only)']}")

    tracker.stop()

    print(tracker.summary())

    assert has_done, "Should have a 'done' event"
    assert len(events) >= 2, "Should have at least step + done events"

    return tracker


def test_general_vision_e2e_launch_wechat():
    """E2E: general vision agent receives 'open WeChat' and executes on mock device."""
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "")

    if not api_key or api_key == "test-key":
        pytest.skip(
            "Skipping live general vision E2E: OPENAI_API_KEY is not configured with a real key"
        )

    if "api.openai.com" in base_url and not api_key.startswith("sk-"):
        pytest.skip(
            "Skipping live general vision E2E: OPENAI_BASE_URL points to OpenAI but key format looks invalid"
        )

    tracker = asyncio.run(run_e2e_test())
    assert len(tracker.records) >= 3, "Should have timing records for all phases"


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
