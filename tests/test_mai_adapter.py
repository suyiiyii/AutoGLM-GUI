"""Unit tests for MAI Agent adapter."""

from unittest.mock import MagicMock, patch

from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

from AutoGLM_GUI.agents.mai_adapter import MAIAgentAdapter, MAIAgentConfig


class TestMAIAgentConfig:
    """Test MAIAgentConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = MAIAgentConfig()
        assert config.history_n == 3
        assert config.max_pixels is None
        assert config.min_pixels is None
        assert config.tools is None
        assert config.use_mai_prompt is False

    def test_custom_values(self):
        """Test custom configuration values."""
        config = MAIAgentConfig(
            history_n=5,
            max_pixels=1024,
            min_pixels=512,
            tools=[{"name": "test"}],
            use_mai_prompt=True,
        )
        assert config.history_n == 5
        assert config.max_pixels == 1024
        assert config.min_pixels == 512
        assert config.tools == [{"name": "test"}]
        assert config.use_mai_prompt is True


class TestCoordinateConversion:
    """Test coordinate conversion between MAI and PhoneAgent scales."""

    def setup_method(self):
        """Set up test fixtures."""
        self.model_config = ModelConfig(
            base_url="http://test.com",
            model_name="test-model",
        )
        self.agent_config = AgentConfig(device_id="test-device")
        self.mai_config = MAIAgentConfig()

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_coordinate_conversion_zero(self, mock_handler, mock_mai_agent):
        """Test coordinate conversion for 0."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        result = adapter._convert_coordinate(0)
        assert result == 0

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_coordinate_conversion_max(self, mock_handler, mock_mai_agent):
        """Test coordinate conversion for 999 (MAI max)."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        result = adapter._convert_coordinate(999)
        assert result == 1000

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_coordinate_conversion_middle(self, mock_handler, mock_mai_agent):
        """Test coordinate conversion for middle value."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        result = adapter._convert_coordinate(500)
        # 500 / 999 * 1000 ≈ 500.5 → 500 (int)
        assert result == 500


class TestActionConversion:
    """Test action format conversion from MAI to PhoneAgent."""

    def setup_method(self):
        """Set up test fixtures."""
        self.model_config = ModelConfig(
            base_url="http://test.com",
            model_name="test-model",
        )
        self.agent_config = AgentConfig(device_id="test-device")
        self.mai_config = MAIAgentConfig()

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_click_action_conversion(self, mock_handler, mock_mai_agent):
        """Test click action conversion."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        mai_action = {
            "action": "click",
            "coordinate": [500, 500],
        }

        result = adapter._convert_action(mai_action)

        assert result["_metadata"] == "do"
        assert result["action"] == "Tap"
        assert "element" in result
        assert len(result["element"]) == 2

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_swipe_action_conversion(self, mock_handler, mock_mai_agent):
        """Test swipe action conversion."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        mai_action = {
            "action": "swipe",
            "direction": "up",
        }

        result = adapter._convert_action(mai_action)

        assert result["_metadata"] == "do"
        assert result["action"] == "Swipe"
        assert "start" in result
        assert "end" in result

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_type_action_conversion(self, mock_handler, mock_mai_agent):
        """Test type action conversion."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        mai_action = {
            "action": "type",
            "text": "hello world",
        }

        result = adapter._convert_action(mai_action)

        assert result["_metadata"] == "do"
        assert result["action"] == "Type"
        assert result["text"] == "hello world"

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_terminate_action_conversion(self, mock_handler, mock_mai_agent):
        """Test terminate action conversion."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        mai_action = {
            "action": "terminate",
            "status": "success",
        }

        result = adapter._convert_action(mai_action)

        assert result["_metadata"] == "finish"
        assert result["message"] == "Task completed"

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_unknown_action_conversion(self, mock_handler, mock_mai_agent):
        """Test unknown action conversion."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        mai_action = {
            "action": "unknown_action",
        }

        result = adapter._convert_action(mai_action)

        assert result["_metadata"] == "finish"
        assert "Unknown action" in result["message"]


class TestSwipeCoordinates:
    """Test swipe coordinate calculation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.model_config = ModelConfig(
            base_url="http://test.com",
            model_name="test-model",
        )
        self.agent_config = AgentConfig(device_id="test-device")
        self.mai_config = MAIAgentConfig()

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_swipe_up(self, mock_handler, mock_mai_agent):
        """Test swipe up direction."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        start, end = adapter._calculate_swipe_coordinates("up", 500, 500)

        assert start[1] > end[1]  # Up: y decreases
        assert start[0] == end[0] == 500  # x stays same

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_swipe_down(self, mock_handler, mock_mai_agent):
        """Test swipe down direction."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        start, end = adapter._calculate_swipe_coordinates("down", 500, 500)

        assert start[1] < end[1]  # Down: y increases
        assert start[0] == end[0] == 500  # x stays same

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_swipe_left(self, mock_handler, mock_mai_agent):
        """Test swipe left direction."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        start, end = adapter._calculate_swipe_coordinates("left", 500, 500)

        assert start[0] > end[0]  # Left: x decreases
        assert start[1] == end[1] == 500  # y stays same

    @patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent")
    @patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler")
    def test_swipe_right(self, mock_handler, mock_mai_agent):
        """Test swipe right direction."""
        mock_mai_agent.return_value = MagicMock()
        mock_handler.return_value = MagicMock()

        adapter = MAIAgentAdapter(
            model_config=self.model_config,
            agent_config=self.agent_config,
            mai_config=self.mai_config,
        )

        start, end = adapter._calculate_swipe_coordinates("right", 500, 500)

        assert start[0] < end[0]  # Right: x increases
        assert start[1] == end[1] == 500  # y stays same


class TestThinkingExtraction:
    """Test thinking extraction from prediction text."""

    def test_extract_thinking_valid(self):
        """Test extraction of valid thinking content."""
        # Need real instance for this test
        model_config = ModelConfig(
            base_url="http://test.com",
            model_name="test-model",
        )
        agent_config = AgentConfig(device_id="test-device")
        mai_config = MAIAgentConfig()

        with (
            patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent"),
            patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler"),
        ):
            adapter = MAIAgentAdapter(
                model_config=model_config,
                agent_config=agent_config,
                mai_config=mai_config,
            )

            text = "<thinking>This is the thinking process</thinking>"
            result = adapter._extract_thinking(text)
            assert result == "This is the thinking process"

    def test_extract_thinking_multiline(self):
        """Test extraction of multiline thinking content."""
        model_config = ModelConfig(
            base_url="http://test.com",
            model_name="test-model",
        )
        agent_config = AgentConfig(device_id="test-device")
        mai_config = MAIAgentConfig()

        with (
            patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent"),
            patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler"),
        ):
            adapter = MAIAgentAdapter(
                model_config=model_config,
                agent_config=agent_config,
                mai_config=mai_config,
            )

            text = """<thinking>
Line 1
Line 2
Line 3
</thinking>"""
            result = adapter._extract_thinking(text)
            assert result == "Line 1\nLine 2\nLine 3"

    def test_extract_thinking_none(self):
        """Test extraction when no thinking tag present."""
        model_config = ModelConfig(
            base_url="http://test.com",
            model_name="test-model",
        )
        agent_config = AgentConfig(device_id="test-device")
        mai_config = MAIAgentConfig()

        with (
            patch("AutoGLM_GUI.agents.mai_adapter.MAIUINaivigationAgent"),
            patch("AutoGLM_GUI.agents.mai_adapter.ActionHandler"),
        ):
            adapter = MAIAgentAdapter(
                model_config=model_config,
                agent_config=agent_config,
                mai_config=mai_config,
            )

            text = "No thinking here"
            result = adapter._extract_thinking(text)
            assert result == ""


class TestAgentFactory:
    """Test agent factory functionality."""

    def test_list_agent_types(self):
        """Test listing registered agent types."""
        from AutoGLM_GUI.agents import list_agent_types

        types = list_agent_types()
        assert isinstance(types, list)
        assert "glm" in types
        assert "mai" in types

    def test_is_agent_type_registered(self):
        """Test checking if agent type is registered."""
        from AutoGLM_GUI.agents import is_agent_type_registered

        assert is_agent_type_registered("glm") is True
        assert is_agent_type_registered("mai") is True
        assert is_agent_type_registered("unknown") is False
