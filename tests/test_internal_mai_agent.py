"""Tests for InternalMAIAgent implementation."""

import base64
from io import BytesIO
from unittest.mock import Mock

import pytest
from PIL import Image

from AutoGLM_GUI.agents.mai.agent import InternalMAIAgent
from AutoGLM_GUI.agents.mai.traj_memory import TrajMemory, TrajStep
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.parsers import MAIParser


@pytest.fixture
def mock_device():
    device = Mock()

    img = Image.new("RGB", (1080, 1920), color="white")
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    img_base64 = base64.b64encode(img_bytes.getvalue()).decode("utf-8")

    screenshot = Mock()
    screenshot.base64_data = img_base64
    screenshot.width = 1080
    screenshot.height = 1920

    device.get_screenshot.return_value = screenshot
    device.get_current_app.return_value = "com.example.app"

    return device


@pytest.fixture
def model_config():
    return ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="test-model",
        api_key="test-key",
    )


@pytest.fixture
def agent_config():
    return AgentConfig(
        max_steps=10,
        device_id="test-device",
        verbose=False,
    )


def test_traj_memory_initialization():
    memory = TrajMemory(task_goal="test task", task_id="123", steps=[])

    assert memory.task_goal == "test task"
    assert memory.task_id == "123"
    assert len(memory) == 0


def test_traj_memory_add_step():
    memory = TrajMemory(task_goal="test", task_id="123", steps=[])

    img = Image.new("RGB", (100, 100))
    step = TrajStep(
        screenshot=img,
        accessibility_tree=None,
        prediction="test prediction",
        action={"action": "click", "coordinate": [0.5, 0.5]},
        conclusion="",
        thought="test thought",
        step_index=0,
        agent_type="InternalMAIAgent",
        model_name="test-model",
        screenshot_bytes=b"test",
    )

    memory.add_step(step)
    assert len(memory) == 1
    assert memory.steps[0].thought == "test thought"


def test_traj_memory_get_history():
    memory = TrajMemory(task_goal="test", task_id="123", steps=[])

    for i in range(5):
        img = Image.new("RGB", (100, 100))
        step = TrajStep(
            screenshot=img,
            accessibility_tree=None,
            prediction=f"pred{i}",
            action={"action": "click"},
            conclusion="",
            thought=f"thought{i}",
            step_index=i,
            agent_type="InternalMAIAgent",
            model_name="test",
            screenshot_bytes=f"bytes{i}".encode(),
        )
        memory.add_step(step)

    images = memory.get_history_images(3)
    assert len(images) == 3
    assert images[-1] == b"bytes4"

    thoughts = memory.get_history_thoughts(2)
    assert len(thoughts) == 2
    assert thoughts[-1] == "thought4"


def test_mai_parser_basic():
    parser = MAIParser()

    response = """<thinking>
我需要点击按钮
</thinking>
<tool_call>
{"name": "mobile_use", "arguments": {"action": "click", "coordinate": [500, 800]}}
</tool_call>"""

    result = parser.parse_with_thinking(response)

    assert result["thinking"] == "我需要点击按钮"
    assert "raw_action" in result
    assert result["raw_action"]["action"] == "click"
    assert len(result["raw_action"]["coordinate"]) == 2
    assert 0 <= result["raw_action"]["coordinate"][0] <= 1
    assert 0 <= result["raw_action"]["coordinate"][1] <= 1


def test_mai_parser_thinking_model_compat():
    parser = MAIParser()

    response = """我需要点击按钮
</think>
<tool_call>
{"name": "mobile_use", "arguments": {"action": "click", "coordinate": [500, 800]}}
</tool_call>"""

    result = parser.parse_with_thinking(response)

    assert "thinking" in result
    assert result["raw_action"]["action"] == "click"


def test_mai_parser_coordinate_normalization():
    parser = MAIParser()

    response = """<thinking>test</thinking>
<tool_call>
{"name": "mobile_use", "arguments": {"action": "click", "coordinate": [999, 999]}}
</tool_call>"""

    result = parser.parse_with_thinking(response)

    x, y = result["raw_action"]["coordinate"]
    assert abs(x - 1.0) < 0.01
    assert abs(y - 1.0) < 0.01


def test_mai_parser_bounding_box():
    parser = MAIParser()

    response = """<thinking>test</thinking>
<tool_call>
{"name": "mobile_use", "arguments": {"action": "click", "coordinate": [100, 200, 300, 400]}}
</tool_call>"""

    result = parser.parse_with_thinking(response)

    x, y = result["raw_action"]["coordinate"]
    assert abs(x - 200 / 999) < 0.01
    assert abs(y - 300 / 999) < 0.01


def test_internal_mai_agent_initialization(mock_device, model_config, agent_config):
    agent = InternalMAIAgent(
        model_config=model_config,
        agent_config=agent_config,
        device=mock_device,
        history_n=3,
    )

    assert agent.history_n == 3
    assert agent.step_count == 0
    assert not agent.is_running
    assert len(agent.traj_memory) == 0


def test_internal_mai_agent_reset(mock_device, model_config, agent_config):
    agent = InternalMAIAgent(
        model_config=model_config,
        agent_config=agent_config,
        device=mock_device,
    )

    agent._step_count = 5
    agent._is_running = True
    agent.traj_memory.add_step(
        TrajStep(
            screenshot=Image.new("RGB", (100, 100)),
            accessibility_tree=None,
            prediction="test",
            action={},
            conclusion="",
            thought="",
            step_index=0,
            agent_type="test",
            model_name="test",
        )
    )

    agent.reset()

    assert agent.step_count == 0
    assert not agent.is_running
    assert len(agent.traj_memory) == 0
