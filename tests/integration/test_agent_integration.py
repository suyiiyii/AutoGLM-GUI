"""Integration tests for Agent state machine testing."""

import pytest
from pathlib import Path

from tests.integration.test_runner import TestRunner


class TestAgentIntegration:
    """Test Agent integration using state machine."""

    def test_sample_case(self, sample_test_case: Path, mock_llm_server: str):
        """Test the sample test case (美团外卖消息按钮)."""
        from AutoGLM_GUI.config import ModelConfig

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
