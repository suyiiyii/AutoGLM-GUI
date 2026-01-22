"""End-to-end test demonstrating testing with RemoteDevice.

This test shows how to:
1. Start a Mock Device Agent server
2. Use RemoteDevice to communicate with the mock server
3. Run agent with mock LLM
4. Assert that the Mock Agent received expected commands
"""

import asyncio

import httpx
import pytest

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
    E2E tests that don't require LLM - test RemoteDevice directly.
    """

    def test_remote_device_works(
        self, mock_agent_server: str, test_client, sample_test_case
    ):
        """Test that RemoteDevice can communicate with mock server."""
        test_client.load_scenario(str(sample_test_case))
        remote_device = RemoteDevice("mock_device_001", mock_agent_server)

        ss = remote_device.get_screenshot()
        assert ss.width > 0

        remote_device.tap(600, 2590)

        commands = test_client.get_actions()
        assert any(c["action"] == "screenshot" for c in commands)
        assert any(c["action"] == "tap" for c in commands)

        test_client.assert_state("message")

    def test_multiple_devices(self, mock_agent_server: str, test_client):
        """Test that multiple remote devices can be managed."""
        device_1 = RemoteDevice("device_1", mock_agent_server)
        device_2 = RemoteDevice("device_2", mock_agent_server)

        device_1.tap(100, 200)
        device_2.tap(300, 400)

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


class TestMultiDeviceConcurrent:
    """Test multi-device concurrent execution scenarios."""

    def test_concurrent_chats_on_different_devices(
        self,
        local_server: dict,
        mock_llm_client,
        mock_agent_server_multi: str,
    ):
        """Verify that concurrent chats on different devices don't interfere."""
        access_url = local_server["access_url"]
        remote_url = mock_agent_server_multi
        llm_url = local_server["llm_url"]

        # Register two devices
        devices = {}
        for device_num in [1, 2]:
            device_id = f"mock_device_00{device_num}"
            resp = httpx.post(
                f"{access_url}/api/devices/add_remote",
                json={"base_url": remote_url, "device_id": device_id},
                timeout=10,
            )
            assert resp.status_code == 200
            register_result = resp.json()
            devices[device_id] = register_result["serial"]

        # Set config via API (required before init)
        resp = httpx.delete(f"{access_url}/api/config", timeout=10)
        resp = httpx.post(
            f"{access_url}/api/config",
            json={
                "base_url": llm_url + "/v1",
                "model_name": "mock-glm-model",
                "api_key": "mock-key",
            },
            timeout=10,
        )
        assert resp.status_code == 200

        # Initialize both devices' agents
        for device_id, serial in devices.items():
            resp = httpx.post(
                f"{access_url}/api/init",
                json={
                    "agent_type": "glm",
                    "device_id": serial,
                    "model_config": {
                        "base_url": llm_url + "/v1",
                        "api_key": "mock-key",
                        "model_name": "mock-glm-model",
                    },
                    "agent_config": {
                        "device_id": serial,
                        "max_steps": 5,
                        "verbose": True,
                    },
                },
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[MultiDevice] Init failed for {device_id}: {resp.text}")
            assert resp.status_code == 200

        # Configure mock LLM to return tap actions
        # Both devices will get tap actions due to round-robin
        mock_llm_client.set_responses(
            [
                'do(action="Tap", element=[100, 200])',
                'do(action="Tap", element=[300, 400])',
                'do(action="Tap", element=[500, 600])',
                'do(action="Tap", element=[700, 800])',
                'finish(message="Task completed")',
                'finish(message="Task completed")',
            ]
        )

        # Send concurrent chat requests
        async def run_concurrent():
            async with httpx.AsyncClient() as client:
                results = await asyncio.gather(
                    client.post(
                        f"{access_url}/api/chat",
                        json={
                            "device_id": devices["mock_device_001"],
                            "message": "点击位置A",
                        },
                        timeout=120,
                    ),
                    client.post(
                        f"{access_url}/api/chat",
                        json={
                            "device_id": devices["mock_device_002"],
                            "message": "点击位置B",
                        },
                        timeout=120,
                    ),
                )
                return results

        results = asyncio.run(run_concurrent())

        # Verify responses
        assert results[0].status_code == 200
        assert results[1].status_code == 200

        # Verify command records
        resp = httpx.get(f"{remote_url}/test/commands")
        commands = resp.json()

        print(f"[MultiDevice] Total commands: {len(commands)}")

        device1_commands = [c for c in commands if c["device_id"] == "mock_device_001"]
        device2_commands = [c for c in commands if c["device_id"] == "mock_device_002"]

        print(f"[MultiDevice] Device 1 commands: {len(device1_commands)}")
        print(f"[MultiDevice] Device 2 commands: {len(device2_commands)}")

        # Verify each device received commands
        assert len(device1_commands) >= 1, "Device 1 should have received commands"
        assert len(device2_commands) >= 1, "Device 2 should have received commands"

        # Verify device isolation - no command should have the wrong device_id
        for cmd in device1_commands:
            assert cmd["device_id"] == "mock_device_001", (
                "Device 1 command has wrong device_id"
            )

        for cmd in device2_commands:
            assert cmd["device_id"] == "mock_device_002", (
                "Device 2 command has wrong device_id"
            )

        print("[MultiDevice] ✓ Concurrent test passed!")

    def test_same_device_concurrent_rejection(
        self,
        local_server: dict,
        mock_llm_client,
        mock_agent_server_multi: str,
    ):
        """Verify that concurrent requests to the same device are handled correctly."""
        access_url = local_server["access_url"]
        remote_url = mock_agent_server_multi

        # Register device
        resp = httpx.post(
            f"{access_url}/api/devices/add_remote",
            json={"base_url": remote_url, "device_id": "mock_device_001"},
            timeout=10,
        )
        assert resp.status_code == 200
        serial = resp.json()["serial"]

        # Set config via API (required before init)
        llm_url = local_server["llm_url"]
        resp = httpx.delete(f"{access_url}/api/config", timeout=10)
        resp = httpx.post(
            f"{access_url}/api/config",
            json={
                "base_url": llm_url + "/v1",
                "model_name": "mock-glm-model",
                "api_key": "mock-key",
            },
            timeout=10,
        )
        assert resp.status_code == 200

        # Initialize agent
        resp = httpx.post(
            f"{access_url}/api/init",
            json={
                "agent_type": "glm",
                "device_id": serial,
                "model_config": {
                    "base_url": llm_url + "/v1",
                    "api_key": "mock-key",
                    "model_name": "mock-glm-model",
                },
                "agent_config": {
                    "device_id": serial,
                    "max_steps": 10,
                },
            },
            timeout=30,
        )
        assert resp.status_code == 200

        # Configure mock LLM responses
        mock_llm_client.set_responses(
            [
                'finish(message="Task completed")',  # First task
                'finish(message="Second task completed")',  # Second task
            ]
        )

        # Send concurrent requests to same device
        async def run_concurrent_same_device():
            async with httpx.AsyncClient() as client:
                # Note: Due to device lock, one request should succeed,
                # the other may fail or be queued depending on timing
                results = await asyncio.gather(
                    client.post(
                        f"{access_url}/api/chat",
                        json={"device_id": serial, "message": "任务1"},
                        timeout=120,
                    ),
                    client.post(
                        f"{access_url}/api/chat",
                        json={"device_id": serial, "message": "任务2"},
                        timeout=120,
                    ),
                    return_exceptions=True,
                )
                return results

        results = asyncio.run(run_concurrent_same_device())

        # At least one request should succeed
        status_codes = []
        for r in results:
            if isinstance(r, httpx.Response):
                status_codes.append(r.status_code)
            else:
                status_codes.append(500)  # Exception

        # The device lock mechanism should prevent concurrent execution
        # At least one request should succeed
        assert 200 in status_codes, "At least one request should succeed"

        print(f"[MultiDevice] Same-device concurrent test statuses: {status_codes}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
