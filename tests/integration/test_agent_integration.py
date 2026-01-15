"""Integration tests for Agent state machine testing."""

from pathlib import Path

import pytest

from tests.integration.test_runner import TestRunner


class TestAgentIntegration:
    """Test Agent integration using state machine."""

    def test_sample_case(
        self, sample_test_case: Path, mock_llm_server: str, mock_llm_client
    ):
        """Test the sample test case (美团外卖消息按钮)."""
        from AutoGLM_GUI.config import ModelConfig

        # Configure Mock LLM with correct coordinates for normalized click_region
        mock_llm_client.set_responses(
            [
                # Response A: First request (find and tap message button)
                """用户要求点击屏幕下方的消息按钮。我需要查看当前截图，找到消息按钮的位置。

从截图中可以看到，这是美团app的主界面。在底部导航���中，我可以看到几个选项：
- 推荐（黄色高亮）
- 视频（有红色数字3的徽章）
- 消息（有红色数字2的徽章）
- 购物车
- 我的

消息按钮在底部导航栏的中间位置，显示为"消息"图标，上面有红色的数字2，表示有2条未读消息。

我需要点击这个消息按钮。根据截图，消息按钮的位置大约在底部导航栏的中间位置，坐标大约是(499, 966)左右。
do(action="Tap", element=[499,966])""",
                # Response B: Second request (finish with success message)
                """好的，我成功点击了消息按钮，现在进入了消息页面。页面显示了各种消息类型，包括：
- 订单动态
- 服务提醒（有2条未读）
- 粉丝福利
- 美团会员
- 美团客服
- 2周前的消息（包括一些加载中的消息）

底部还有一个通知提示"开启通知，获取外卖订单进度"。

任务已经完成，我成功点击了屏幕下方的消息按钮，现在进入了消息页面。
finish(message="已成功点击消息按钮！现在进入了消息页面，可以看到各类消息通知，包括订单动态、服务提醒（有2条未读）、美团会员、美团客服以及2周前的历史消息。")""",
            ]
        )

        # Use mock LLM config
        model_config = ModelConfig(
            base_url=mock_llm_server + "/v1",
            api_key="mock-key",
            model_name="mock-glm-model",
        )

        runner = TestRunner(sample_test_case)
        result = runner.run(model_config=model_config)

        assert result["passed"], f"Test failed: {result['failure_reason']}"
        assert result["final_state"] == "message"

    def test_state_machine_loading(self, sample_test_case: Path):
        """Test that test case loads correctly."""
        from tests.integration.state_machine import load_test_case

        state_machine, instruction, max_steps = load_test_case(sample_test_case)

        assert instruction == "点击屏幕下方的消息按钮"
        assert max_steps == 10
        assert "home" in state_machine.states
        assert "message" in state_machine.states
        assert state_machine.current_state_id == "home"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
