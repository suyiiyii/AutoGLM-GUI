"""End-to-end test demonstrating non-invasive testing with RemoteDevice.

This test shows how to:
1. Start a Mock Device Agent server
2. Inject RemoteDevice into agent via DeviceProtocolAdapter
3. Run agent with real LLM
4. Assert that the Mock Agent received expected commands

This is completely non-invasive - no modifications to AutoGLM-GUI code.
"""

import multiprocessing
import time
from pathlib import Path
from typing import cast

import pytest
import uvicorn

from AutoGLM_GUI.device_adapter import DeviceProtocolContext, DeviceProtocolAdapter
from AutoGLM_GUI.devices.remote_device import RemoteDevice
from tests.integration.device_agent.test_client import MockAgentTestClient


def run_server(port: int):
    """Run the mock agent server in a subprocess."""
    from tests.integration.device_agent.mock_agent_server import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture(scope="module")
def mock_agent_server():
    """Start mock agent server for testing."""
    port = 18002
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


class TestE2EWithAgent:
    """
    End-to-end tests with real GLMAgent.

    These tests require LLM API credentials in environment:
    - AUTOGLM_BASE_URL
    - AUTOGLM_API_KEY
    - AUTOGLM_MODEL_NAME
    """

    def test_agent_tap_recorded_by_mock(
        self,
        mock_agent_server: str,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test that agent's tap commands are recorded by mock agent."""
        from AutoGLM_GUI.agents.glm.agent import GLMAgent
        from AutoGLM_GUI.config import AgentConfig, ModelConfig
        from AutoGLM_GUI.config_manager import config_manager

        test_client.load_scenario(scenario_path)

        config_manager.load_env_config()
        config_manager.load_file_config()
        effective_config = config_manager.get_effective_config()

        model_config = ModelConfig(
            base_url=effective_config.base_url,
            api_key=effective_config.api_key,
            model_name=effective_config.model_name,
        )

        agent_config = AgentConfig(
            max_steps=5,
            device_id="mock_device_001",
            verbose=True,
        )

        remote_device = RemoteDevice("mock_device_001", mock_agent_server)

        with DeviceProtocolContext(
            get_device=lambda _: remote_device,
            default_device_id="mock_device_001",
        ):
            agent = GLMAgent(
                model_config=model_config,
                agent_config=agent_config,
                device=remote_device,
            )

            agent.run("点击屏幕下方的消息按钮")

        commands = test_client.get_actions()
        tap_commands = [c for c in commands if c["action"] == "tap"]

        assert len(tap_commands) >= 1, (
            f"Expected at least 1 tap, got {len(tap_commands)}"
        )

        test_client.assert_tap_in_region(487, 2516, 721, 2667)

        test_client.assert_state("message")


class TestE2EWithoutLLM:
    """
    E2E tests that don't require LLM - test the injection mechanism.
    """

    def test_remote_device_injection_works(
        self,
        mock_agent_server: str,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test that RemoteDevice can be injected via adapter."""
        test_client.load_scenario(scenario_path)
        remote_device = RemoteDevice("mock_device_001", mock_agent_server)

        with DeviceProtocolContext(
            get_device=lambda _: remote_device,
            default_device_id="mock_device_001",
        ) as adapter:
            factory = cast(DeviceProtocolAdapter, adapter)

            ss = factory.get_screenshot("mock_device_001")
            assert ss.width > 0

            factory.tap(600, 2590, "mock_device_001")

        commands = test_client.get_actions()
        assert any(c["action"] == "screenshot" for c in commands)
        assert any(c["action"] == "tap" for c in commands)

        test_client.assert_state("message")

    def test_multiple_devices(
        self,
        mock_agent_server: str,
        test_client: MockAgentTestClient,
    ):
        """Test that multiple remote devices can be managed."""
        devices = {
            "device_1": RemoteDevice("device_1", mock_agent_server),
            "device_2": RemoteDevice("device_2", mock_agent_server),
        }

        with DeviceProtocolContext(
            get_device=lambda did: devices.get(did or "device_1", devices["device_1"]),
            default_device_id="device_1",
        ) as adapter:
            factory = cast(DeviceProtocolAdapter, adapter)

            factory.tap(100, 200, "device_1")
            factory.tap(300, 400, "device_2")

        commands = test_client.get_commands()

        device_1_taps = [c for c in commands if c["device_id"] == "device_1"]
        device_2_taps = [c for c in commands if c["device_id"] == "device_2"]

        assert len(device_1_taps) == 1
        assert len(device_2_taps) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
