"""Test ModelClient._parse_response action priority logic."""

from AutoGLM_GUI.model.client import ModelClient
from AutoGLM_GUI.model.types import VisionModelConfig


def test_do_action_takes_priority_over_finish():
    config = VisionModelConfig(base_url="http://dummy", model_name="test")
    client = ModelClient(config)

    raw_content = """淘宝应用正在启动
finish(message="等待启动")
do(action="Wait", duration="1 seconds")"""

    thinking, action = client._parse_response(raw_content)

    assert action == 'do(action="Wait", duration="1 seconds")'
    assert "淘宝应用正在启动" in thinking


def test_finish_only_when_no_do_action():
    config = VisionModelConfig(base_url="http://dummy", model_name="test")
    client = ModelClient(config)

    raw_content = """任务完成
finish(message="Done")"""

    thinking, action = client._parse_response(raw_content)

    assert action == 'finish(message="Done")'
    assert thinking == "任务完成"


def test_do_action_found_first():
    config = VisionModelConfig(base_url="http://dummy", model_name="test")
    client = ModelClient(config)

    raw_content = """观察屏幕
do(action="Tap", element=[500, 500])
一些其他文本
finish(message="完成")"""

    thinking, action = client._parse_response(raw_content)

    assert action == 'do(action="Tap", element=[500, 500])'
    assert thinking == "观察屏幕"


def test_with_answer_tags():
    config = VisionModelConfig(base_url="http://dummy", model_name="test")
    client = ModelClient(config)

    raw_content = (
        '<think>分析中</think><answer>do(action="Wait", duration="2 seconds")</answer>'
    )

    thinking, action = client._parse_response(raw_content)

    assert thinking == "分析中"
    assert action == 'do(action="Wait", duration="2 seconds")'


def test_multiline_thinking_with_do():
    config = VisionModelConfig(base_url="http://dummy", model_name="test")
    client = ModelClient(config)

    raw_content = """我看到了淘宝的启动画面
显示"万能的淘宝"和购物、外卖、旅行的标语
需要等待加载完成
do(action="Wait", duration="1 seconds")"""

    thinking, action = client._parse_response(raw_content)

    assert action == 'do(action="Wait", duration="1 seconds")'
    assert "淘宝的启动画面" in thinking
    assert "等待加载完成" in thinking


def test_bug_finish_with_embedded_do_in_message():
    config = VisionModelConfig(base_url="http://dummy", model_name="test")
    client = ModelClient(config)

    raw_content = """淘宝应用正在启动，我看到了淘宝的启动画面，显示"万能的淘宝"和购物、外卖、旅行的标语，以及一个橙色的购物车图标。这是启动页面，我需要等待它加载完成进入主界面。我应该等待一下让应用完全加载。
do(action="Wait", duration="1 seconds")"""

    thinking, action = client._parse_response(raw_content)

    assert action == 'do(action="Wait", duration="1 seconds")'
    assert "淘宝应用正在启动" in thinking
