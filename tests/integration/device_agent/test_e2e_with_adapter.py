"""End-to-end test demonstrating non-invasive testing with RemoteDevice.

This test shows how to:
1. Start a Mock Device Agent server
2. Inject RemoteDevice into agent via DeviceProtocolAdapter
3. Run agent with real LLM
4. Assert that the Mock Agent received expected commands

This is completely non-invasive - no modifications to AutoGLM-GUI code.
"""

from typing import cast

import pytest

from AutoGLM_GUI.device_adapter import DeviceProtocolAdapter, DeviceProtocolContext
from AutoGLM_GUI.devices.remote_device import RemoteDevice


class TestE2EWithAgent:
    """
    End-to-end tests with GLMAgent using Mock LLM.

    These tests use the mock LLM server and don't require real API credentials.
    """

    def test_agent_tap_recorded_by_mock(
        self,
        mock_llm_server: str,  # Mock LLM server
        mock_agent_server: str,  # Mock device server
        mock_llm_client,  # Mock LLM client
        test_client,  # Mock device client
        sample_test_case,
    ):
        """Test that agent's tap commands are recorded by mock agent."""
        from AutoGLM_GUI.agents.glm.agent import GLMAgent
        from AutoGLM_GUI.config import AgentConfig, ModelConfig

        test_client.load_scenario(str(sample_test_case))

        # Configure mock LLM (no real credentials needed!)
        model_config = ModelConfig(
            base_url=mock_llm_server + "/v1",
            api_key="mock-key",
            model_name="mock-glm-model",
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

        # Verify mock LLM was called twice (tap + finish)
        mock_llm_client.assert_request_count(2)

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
        self, mock_agent_server: str, test_client, sample_test_case
    ):
        """Test that RemoteDevice can be injected via adapter."""
        test_client.load_scenario(str(sample_test_case))
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

    def test_multiple_devices(self, mock_agent_server: str, test_client):
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


class TestE2EWithMockLLM:
    """
    E2E tests with Mock LLM server (no credentials needed).

    These tests use both Mock LLM and Mock Device servers,
    enabling complete testing without any external dependencies.
    """

    def test_agent_tap_with_mock_llm(
        self,
        mock_llm_server: str,  # Mock LLM server
        mock_agent_server: str,  # Mock device server
        mock_llm_client,  # Mock LLM client
        test_client,  # Mock device client
        sample_test_case,
    ):
        """Test agent with mock LLM and mock device - no credentials required."""
        from AutoGLM_GUI.agents.glm.agent import GLMAgent
        from AutoGLM_GUI.config import AgentConfig, ModelConfig

        # Load test scenario
        test_client.load_scenario(str(sample_test_case))

        # Configure mock LLM (no real credentials needed!)
        model_config = ModelConfig(
            base_url=mock_llm_server + "/v1",  # Mock LLM endpoint
            api_key="mock-key",  # Any value works
            model_name="mock-glm-model",
        )

        agent_config = AgentConfig(
            max_steps=5,
            device_id="mock_device_001",
            verbose=True,
        )

        # Create remote device
        remote_device = RemoteDevice("mock_device_001", mock_agent_server)

        # Run agent with mock LLM and mock device
        with DeviceProtocolContext(
            get_device=lambda _: remote_device,
            default_device_id="mock_device_001",
        ):
            agent = GLMAgent(
                model_config=model_config,
                agent_config=agent_config,
                device=remote_device,
            )

            # Execute task
            agent.run("点击屏幕下方的消息按钮")

        # Verify mock LLM was called twice (tap + finish)
        mock_llm_client.assert_request_count(2)

        # Verify device received tap command
        commands = test_client.get_actions()
        tap_commands = [c for c in commands if c["action"] == "tap"]

        assert len(tap_commands) >= 1, (
            f"Expected at least 1 tap, got {len(tap_commands)}"
        )

        # Verify tap was in correct region
        test_client.assert_tap_in_region(487, 2516, 721, 2667)

        # Verify final state
        test_client.assert_state("message")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
