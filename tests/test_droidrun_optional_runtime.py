"""Exercise the adapter against the installed optional runtime without device I/O."""

import asyncio
import importlib.util
from types import SimpleNamespace

import pytest

from AutoGLM_GUI.agents.droidrun.async_agent import DroidRunAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig


def test_droidrun_real_config_and_events(monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("droidrun") is None:
        pytest.skip("Install the droidrun extra to verify the real runtime")

    from droidrun.agent.droid.droid_agent import DroidAgent
    from droidrun.agent.droid.events import CodeActResultEvent, ResultEvent
    from droidrun.agent.utils import llm_picker
    from droidrun.config_manager.config_manager import DroidrunConfig

    captured = {}

    # Keep real imports, configuration, and event models; stop at external I/O.
    def capture_init(self, goal, llms, config):
        captured.update(goal=goal, config=config)

    class Handler:
        async def stream_events(self):
            yield CodeActResultEvent(
                success=True, reason="step complete", instruction="tap"
            )
            yield ResultEvent(success=True, reason="task complete", steps=1)

    monkeypatch.setattr(llm_picker, "load_llm", lambda *args, **kwargs: object())
    monkeypatch.setattr(DroidAgent, "__init__", capture_init)
    monkeypatch.setattr(DroidAgent, "run", lambda self: Handler())
    adapter = DroidRunAgent(
        ModelConfig(),
        AgentConfig(max_steps=7),
        SimpleNamespace(device_id="test-device"),
    )

    async def collect():
        return [event async for event in adapter.stream("tap the button")]

    events = asyncio.run(collect())
    assert [event["type"] for event in events] == ["thinking", "step", "done"]
    assert events[1]["data"]["thinking"] == "step complete"
    assert events[1]["data"]["action"]["description"] == "tap"
    assert events[-1]["data"] == {
        "success": True,
        "message": "task complete",
        "steps": 1,
    }
    assert captured["goal"] == "tap the button"
    config = captured["config"]
    assert isinstance(config, DroidrunConfig)
    assert config.device.serial == "test-device"
    assert config.telemetry.enabled is False
    assert config.agent.max_steps == 7
    assert config.agent.reasoning is False
