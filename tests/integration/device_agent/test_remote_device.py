"""Tests for RemoteDevice + Mock Device Agent integration.

These tests demonstrate the non-invasive testing approach:
1. Start Mock Device Agent server
2. Use RemoteDevice to send commands
3. Assert commands were recorded correctly
"""

import multiprocessing
import time
from pathlib import Path

import pytest
import uvicorn

from AutoGLM_GUI.devices.remote_device import RemoteDevice
from tests.integration.device_agent.test_client import MockAgentTestClient


def run_server(port: int):
    """Run the mock agent server in a subprocess."""
    from tests.integration.device_agent.mock_agent_server import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture(scope="module")
def mock_agent_server():
    """Start mock agent server for testing."""
    port = 18001
    proc = multiprocessing.Process(target=run_server, args=(port,), daemon=True)
    proc.start()
    time.sleep(1)

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    proc.join(timeout=2)


@pytest.fixture
def test_client(mock_agent_server: str) -> MockAgentTestClient:
    """Create test client and reset state."""
    client = MockAgentTestClient(mock_agent_server)
    client.reset()
    return client


@pytest.fixture
def scenario_path() -> str:
    """Get path to test scenario."""
    return str(
        Path(__file__).parent.parent
        / "fixtures"
        / "scenarios"
        / "meituan_message"
        / "scenario.yaml"
    )


class TestRemoteDeviceBasic:
    """Basic RemoteDevice tests."""

    def test_tap_records_command(
        self, mock_agent_server: str, test_client: MockAgentTestClient
    ):
        """Test that tap is recorded by mock agent."""
        device = RemoteDevice("mock_001", mock_agent_server)

        device.tap(100, 200)

        commands = test_client.get_actions()
        assert len(commands) == 1
        assert commands[0]["action"] == "tap"
        assert commands[0]["x"] == 100
        assert commands[0]["y"] == 200

    def test_swipe_records_command(
        self, mock_agent_server: str, test_client: MockAgentTestClient
    ):
        """Test that swipe is recorded by mock agent."""
        device = RemoteDevice("mock_001", mock_agent_server)

        device.swipe(100, 200, 300, 400, duration_ms=500)

        commands = test_client.get_actions()
        assert len(commands) == 1
        assert commands[0]["action"] == "swipe"
        assert commands[0]["start_x"] == 100
        assert commands[0]["end_y"] == 400

    def test_multiple_commands(
        self, mock_agent_server: str, test_client: MockAgentTestClient
    ):
        """Test multiple commands are recorded in order."""
        device = RemoteDevice("mock_001", mock_agent_server)

        device.tap(100, 200)
        device.swipe(100, 200, 300, 400)
        device.tap(500, 600)
        device.back()

        test_client.assert_actions(["tap", "swipe", "tap", "back"])

    def test_type_text(self, mock_agent_server: str, test_client: MockAgentTestClient):
        """Test type_text is recorded."""
        device = RemoteDevice("mock_001", mock_agent_server)

        device.type_text("Hello World")

        commands = test_client.get_actions()
        assert commands[0]["action"] == "type_text"
        assert commands[0]["text"] == "Hello World"


class TestRemoteDeviceWithStateMachine:
    """Tests with state machine backing."""

    def test_tap_triggers_state_transition(
        self,
        mock_agent_server: str,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test that tap triggers state machine transition."""
        test_client.load_scenario(scenario_path)
        device = RemoteDevice("mock_001", mock_agent_server)

        state_before = test_client.get_state()
        assert state_before["current_state"] == "home"

        device.tap(600, 2590)

        test_client.assert_state("message")

    def test_screenshot_returns_state_image(
        self,
        mock_agent_server: str,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test that screenshot returns current state's image."""
        test_client.load_scenario(scenario_path)
        device = RemoteDevice("mock_001", mock_agent_server)

        screenshot = device.get_screenshot()

        assert screenshot.width > 0
        assert screenshot.height > 0
        assert len(screenshot.base64_data) > 0

    def test_current_app_from_state(
        self,
        mock_agent_server: str,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test that current_app returns state machine's app."""
        test_client.load_scenario(scenario_path)
        device = RemoteDevice("mock_001", mock_agent_server)

        app = device.get_current_app()

        assert app == "com.sankuai.meituan"

    def test_tap_in_region_assertion(
        self,
        mock_agent_server: str,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test tap region assertion helper."""
        test_client.load_scenario(scenario_path)
        device = RemoteDevice("mock_001", mock_agent_server)

        device.tap(600, 2590)

        test_client.assert_tap_in_region(487, 2516, 721, 2667)


class TestMockAgentAssertionAPI:
    """Test the assertion API of Mock Agent."""

    def test_expect_matching_actions(
        self, mock_agent_server: str, test_client: MockAgentTestClient
    ):
        """Test expect API with matching actions."""
        device = RemoteDevice("mock_001", mock_agent_server)
        device.tap(100, 200)
        device.swipe(0, 0, 100, 100)

        result = test_client.expect(["tap", "swipe"])

        assert result["match"] is True

    def test_expect_mismatching_actions(
        self, mock_agent_server: str, test_client: MockAgentTestClient
    ):
        """Test expect API with mismatching actions."""
        device = RemoteDevice("mock_001", mock_agent_server)
        device.tap(100, 200)

        result = test_client.expect(["swipe"])

        assert result["match"] is False
        assert "tap" in result["actual"]

    def test_reset_clears_commands(
        self, mock_agent_server: str, test_client: MockAgentTestClient
    ):
        """Test that reset clears command history."""
        device = RemoteDevice("mock_001", mock_agent_server)
        device.tap(100, 200)

        assert len(test_client.get_commands()) == 1

        test_client.reset()

        assert len(test_client.get_commands()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
