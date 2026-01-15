"""Local end-to-end integration tests (without Docker).

This test module runs AutoGLM-GUI server locally and communicates
with a Mock Device Agent and Mock LLM server, providing the same
test coverage as test_docker_e2e.py but without requiring Docker.

Prerequisites:
    - None (runs entirely in local Python processes)
"""

import multiprocessing
from pathlib import Path

import httpx
import pytest

from tests.integration.conftest import find_free_port, wait_for_server


def _run_autoglm_server(port: int, llm_url: str):
    """Run AutoGLM-GUI server in a subprocess."""
    import uvicorn

    # Delete config file to use environment variables
    import os

    os.environ["AUTOGLM_BASE_URL"] = llm_url + "/v1"
    os.environ["AUTOGLM_MODEL_NAME"] = "mock-glm-model"
    os.environ["AUTOGLM_API_KEY"] = "mock-key"
    os.environ["HOME"] = "/tmp"  # Override HOME to avoid loading user config

    # Import and run the server
    from AutoGLM_GUI.server import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture
def local_server(mock_llm_server: str, mock_agent_server: str):
    """Start AutoGLM-GUI server locally (function-scoped for isolation).

    Each test gets a fresh server instance on a unique port.

    Returns:
        Dict with server URLs and configuration
    """
    port = find_free_port(start=8000, end=8099)
    access_url = f"http://127.0.0.1:{port}"
    remote_url = mock_agent_server
    llm_url = mock_llm_server

    print(f"\n[Local E2E] Starting server on port {port}")
    print(f"[Local E2E] Access URL: {access_url}")
    print(f"[Local E2E] LLM URL: {llm_url}")

    # Start server in subprocess
    proc = multiprocessing.Process(
        target=_run_autoglm_server, args=(port, llm_url), daemon=True
    )
    proc.start()

    print("[Local E2E] Waiting for server to start...")
    try:
        wait_for_server(access_url, timeout=30.0, endpoint="/api/health")
        print("[Local E2E] Server is ready!")
    except RuntimeError as e:
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
        raise RuntimeError(f"Server failed to start: {e}")

    yield {
        "access_url": access_url,
        "remote_url": remote_url,  # Will be set by test
        "llm_url": llm_url,
        "port": port,
    }

    # Cleanup: Stop server
    print(f"[Local E2E] Stopping server on port {port}")
    proc.terminate()
    proc.join(timeout=2)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=1)


class TestLocalE2E:
    """End-to-end tests with AutoGLM-GUI running locally (no Docker)."""

    def test_meituan_message_scenario(
        self,
        local_server: dict,
        mock_llm_client,
        mock_agent_server: str,
        test_client,
        sample_test_case: Path,
    ):
        """Test complete flow: Local server -> Mock LLM -> Mock Agent.

        This test provides the same coverage as test_docker_e2e.py::TestDockerE2E::test_meituan_message_scenario
        but runs the server locally instead of in a Docker container.
        """
        # Update local_server with actual mock_agent_server URL
        local_server["remote_url"] = mock_agent_server

        access_url = local_server["access_url"]
        remote_url = local_server["remote_url"]
        llm_url = local_server["llm_url"]

        test_client.load_scenario(str(sample_test_case))

        print(f"[Local E2E] Registering remote device at {access_url}")
        print(f"[Local E2E] Remote URL: {remote_url}")

        # Clean up any existing devices with matching serial
        try:
            resp = httpx.get(f"{access_url}/api/devices", timeout=10)
            if resp.status_code == 200:
                devices = resp.json()["devices"]
                for device in devices:
                    if device.get("model") == "mock_device_001":
                        device_id = device["id"]
                        resp = httpx.delete(
                            f"{access_url}/api/devices/{device_id}",
                            timeout=10,
                        )
                        print(
                            f"[Local E2E] Cleaned up existing device {device_id}: {resp.status_code}"
                        )
        except Exception as e:
            print(f"[Local E2E] Failed to cleanup devices: {e}")

        # Register remote device
        resp = httpx.post(
            f"{access_url}/api/devices/add_remote",
            json={
                "base_url": remote_url,
                "device_id": "mock_device_001",
            },
            timeout=10,
        )
        assert resp.status_code == 200, f"Failed to register device: {resp.text}"

        register_result = resp.json()
        print(f"[Local E2E] Device registered: {register_result}")

        if not register_result["success"]:
            error_msg = register_result.get("message", "Unknown error")
            print(f"[Local E2E] ERROR: Remote device registration failed: {error_msg}")
            pytest.fail(f"Remote device registration failed: {error_msg}")

        registered_serial = register_result["serial"]
        print(f"[Local E2E] Registered device serial: {registered_serial}")

        # Verify device discovery
        print(f"[Local E2E] Verifying device discovery at {access_url}")
        resp = httpx.get(f"{access_url}/api/devices", timeout=10)
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        print(f"[Local E2E] Found {len(devices)} device(s): {devices}")

        # Find the remote device we just registered
        remote_devices = [d for d in devices if d["serial"] == registered_serial]
        assert len(remote_devices) > 0, (
            f"Registered remote device {registered_serial} not found in device list. "
            f"Available devices: {[d['serial'] for d in devices]}"
        )

        registered_device_id = remote_devices[0]["id"]
        print(f"[Local E2E] Using remote device_id: {registered_device_id}")

        # Initialize agent
        print(f"[Local E2E] Initializing agent at {access_url}")
        print(f"[Local E2E] Using Mock LLM at: {llm_url}")

        # Delete existing config file to use environment variables
        try:
            resp = httpx.delete(f"{access_url}/api/config", timeout=10)
            print(f"[Local E2E] Deleted existing config: {resp.status_code}")
        except Exception as e:
            print(f"[Local E2E] No config to delete: {e}")

        # Create new config via API
        resp = httpx.post(
            f"{access_url}/api/config",
            json={
                "base_url": llm_url + "/v1",
                "model_name": "mock-glm-model",
                "api_key": "mock-key",
            },
            timeout=10,
        )
        assert resp.status_code == 200, f"Failed to save config: {resp.text}"
        print(f"[Local E2E] Saved new config: {resp.json()}")

        resp = httpx.post(
            f"{access_url}/api/init",
            json={
                "agent_type": "glm",
                "device_id": registered_device_id,
                "model_config": {
                    "base_url": llm_url + "/v1",
                    "api_key": "mock-key",
                    "model_name": "mock-glm-model",
                },
                "agent_config": {
                    "device_id": registered_device_id,
                    "max_steps": 10,
                    "verbose": True,
                },
            },
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"[Local E2E] ERROR: Init failed with status {resp.status_code}")
            print(f"[Local E2E] Response: {resp.text}")
        assert resp.status_code == 200, f"Init failed: {resp.text}"
        print(f"[Local E2E] Init response: {resp.json()}")

        # Send chat message
        instruction = "点击屏幕下方的消息按钮"
        print(f"[Local E2E] Sending instruction: {instruction}")
        resp = httpx.post(
            f"{access_url}/api/chat",
            json={
                "device_id": registered_device_id,
                "message": instruction,
            },
            timeout=120,
        )
        assert resp.status_code == 200

        result = resp.json()
        print(f"[Local E2E] Chat result: {result}")

        # Verify Mock LLM was called
        print("[Local E2E] Verifying Mock LLM calls...")
        mock_llm_stats = mock_llm_client.get_stats()
        print(f"[Local E2E] Mock LLM request count: {mock_llm_stats['request_count']}")
        assert mock_llm_stats["request_count"] == 2, (
            f"Expected 2 LLM requests, got {mock_llm_stats['request_count']}"
        )

        # Verify device commands
        print("[Local E2E] Checking mock agent for recorded commands...")
        commands = test_client.get_commands()
        print(f"[Local E2E] Total commands recorded: {len(commands)}")
        for i, cmd in enumerate(commands):
            print(f"[Local E2E]   Command {i + 1}: {cmd}")

        tap_commands = [c for c in commands if c["action"] == "tap"]
        print(f"[Local E2E] Tap commands: {tap_commands}")
        assert len(tap_commands) >= 1, (
            f"Expected at least 1 tap, got {len(tap_commands)}. All commands: {commands}"
        )

        tap = tap_commands[0]
        x, y = tap["params"]["x"], tap["params"]["y"]
        # Expected pixel coordinates for click_region [487, 2516, 721, 2667] on 1200x2670 screen
        assert 487 <= x <= 721, f"Tap x={x} not in message button region [487, 721]"
        assert 2516 <= y <= 2667, f"Tap y={y} not in message button region [2516, 2667]"

        state = test_client.get_state()
        assert state["current_state"] == "message", (
            f"Expected state 'message', got '{state['current_state']}'"
        )

        print("[Local E2E] ✓ Test passed!")

    def test_wechat_multi_step_scenario(
        self,
        local_server: dict,
        mock_llm_client,
        mock_agent_server: str,
        test_client,
    ):
        """Test 10-step WeChat scenario.

        Tests a complex 10-step workflow:
        1. Open WeChat from home screen
        2. Tap search button
        3. Tap search box
        4. Tap first contact in search results
        5. Tap input field
        6. Confirm input active
        7. Tap send button
        8. Tap back button
        9. Confirm back action
        10. Finish
        """
        # Update local_server with actual mock_agent_server URL
        local_server["remote_url"] = mock_agent_server

        access_url = local_server["access_url"]
        remote_url = local_server["remote_url"]
        llm_url = local_server["llm_url"]

        # Load WeChat test scenario
        scenario_path = (
            Path(__file__).parent
            / "fixtures"
            / "scenarios"
            / "wechat_multi_step"
            / "scenario.yaml"
        )
        test_client.load_scenario(str(scenario_path))

        print(f"[Local E2E] Registering remote device at {access_url}")
        print(f"[Local E2E] Remote URL: {remote_url}")

        # Clean up any existing devices with matching serial
        try:
            resp = httpx.get(f"{access_url}/api/devices", timeout=10)
            if resp.status_code == 200:
                devices = resp.json()["devices"]
                for device in devices:
                    if device.get("model") == "mock_device_001":
                        device_id = device["id"]
                        resp = httpx.delete(
                            f"{access_url}/api/devices/{device_id}",
                            timeout=10,
                        )
                        print(
                            f"[Local E2E] Cleaned up existing device {device_id}: {resp.status_code}"
                        )
        except Exception as e:
            print(f"[Local E2E] Failed to cleanup devices: {e}")

        # Register remote device
        resp = httpx.post(
            f"{access_url}/api/devices/add_remote",
            json={
                "base_url": remote_url,
                "device_id": "mock_device_001",
            },
            timeout=10,
        )
        assert resp.status_code == 200, f"Failed to register device: {resp.text}"

        register_result = resp.json()
        print(f"[Local E2E] Device registered: {register_result}")

        if not register_result["success"]:
            error_msg = register_result.get("message", "Unknown error")
            print(f"[Local E2E] ERROR: Remote device registration failed: {error_msg}")
            pytest.fail(f"Remote device registration failed: {error_msg}")

        registered_serial = register_result["serial"]
        print(f"[Local E2E] Registered device serial: {registered_serial}")

        # Verify device discovery
        print(f"[Local E2E] Verifying device discovery at {access_url}")
        resp = httpx.get(f"{access_url}/api/devices", timeout=10)
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        print(f"[Local E2E] Found {len(devices)} device(s): {devices}")

        # Find the remote device we just registered
        remote_devices = [d for d in devices if d["serial"] == registered_serial]
        assert len(remote_devices) > 0, (
            f"Registered remote device {registered_serial} not found in device list. "
            f"Available devices: {[d['serial'] for d in devices]}"
        )

        registered_device_id = remote_devices[0]["id"]
        print(f"[Local E2E] Using remote device_id: {registered_device_id}")

        # Initialize agent
        print(f"[Local E2E] Initializing agent at {access_url}")
        print(f"[Local E2E] Using Mock LLM at: {llm_url}")

        # Delete existing config file to use environment variables
        try:
            resp = httpx.delete(f"{access_url}/api/config", timeout=10)
            print(f"[Local E2E] Deleted existing config: {resp.status_code}")
        except Exception as e:
            print(f"[Local E2E] No config to delete: {e}")

        # Create new config via API
        resp = httpx.post(
            f"{access_url}/api/config",
            json={
                "base_url": llm_url + "/v1",
                "model_name": "mock-glm-model",
                "api_key": "mock-key",
            },
            timeout=10,
        )
        assert resp.status_code == 200, f"Failed to save config: {resp.text}"
        print(f"[Local E2E] Saved new config: {resp.json()}")

        resp = httpx.post(
            f"{access_url}/api/init",
            json={
                "agent_type": "glm",
                "device_id": registered_device_id,
                "model_config": {
                    "base_url": llm_url + "/v1",
                    "api_key": "mock-key",
                    "model_name": "mock-glm-model",
                },
                "agent_config": {
                    "device_id": registered_device_id,
                    "max_steps": 15,  # Allow some buffer
                    "verbose": True,
                },
            },
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"[Local E2E] ERROR: Init failed with status {resp.status_code}")
            print(f"[Local E2E] Response: {resp.text}")
        assert resp.status_code == 200, f"Init failed: {resp.text}"
        print(f"[Local E2E] Init response: {resp.json()}")

        # Configure Mock LLM with 10-step response sequence
        mock_llm_client.set_responses(
            [
                # Step 1: Open WeChat
                """用户要求打开微信并搜索'张三'。我看到桌面上有微信图标。
                do(action="Tap", element=[250, 850])""",
                # Step 2: Tap search button
                """现在进入微信主界面，需要点击搜索按钮。
                do(action="Tap", element=[850, 100])""",
                # Step 3: Tap search box
                """进入搜索页面，需要点击搜索框输入文字。
                do(action="Tap", element=[500, 100])""",
                # Step 4: Tap first contact
                """搜索结果显示了多个联系人，点击第一个'张三'。
                do(action="Tap", element=[500, 350])""",
                # Step 5: Tap input field
                """进入张三的聊天界面，需要点击输入框输入消息。
                do(action="Tap", element=[500, 800])""",
                # Step 6: Confirm input active
                """输入框已激活，确认焦点位置。
                do(action="Tap", element=[550, 800])""",
                # Step 7: Tap send button
                """消息'你好'已输入，准备发送。
                do(action="Tap", element=[925, 800])""",
                # Step 8: Tap back button
                """消息已发送成功，现在返回聊天列表。
                do(action="Tap", element=[100, 150])""",
                # Step 9: Confirm back
                """已返回聊天列表，所有操作完成。
                do(action="Tap", element=[550, 550])""",
                # Step 10: Finish
                """任务完成！已成功执行所有10个步骤：
                1. 打开微信
                2. 点击搜索按钮
                3. 点击搜索框
                4. 选择联系人'张三'
                5. 点击输入框
                6. 激活输入
                7. 发送消息'你好'
                8. 返回聊天列表
                9. 确认返回
                10. 任务完成
                finish(message="成功完成10步微信操作任务！")""",
            ]
        )

        # Send chat instruction
        instruction = "打开微信，搜索'张三'，发送消息'你好'"
        print(f"[Local E2E] Sending instruction: {instruction}")
        resp = httpx.post(
            f"{access_url}/api/chat",
            json={
                "device_id": registered_device_id,
                "message": instruction,
            },
            timeout=180,  # 10 steps need more time
        )
        assert resp.status_code == 200

        result = resp.json()
        print(f"[Local E2E] Chat result: {result}")

        # Verify Mock LLM was called 10 times (all tap steps)
        # Note: finish() may not be called if max_steps is reached
        print("[Local E2E] Verifying Mock LLM calls...")
        mock_llm_stats = mock_llm_client.get_stats()
        print(f"[Local E2E] Mock LLM request count: {mock_llm_stats['request_count']}")
        assert mock_llm_stats["request_count"] == 10, (
            f"Expected 10 LLM requests, got {mock_llm_stats['request_count']}"
        )

        # Verify device commands
        print("[Local E2E] Checking mock agent for recorded commands...")
        commands = test_client.get_commands()
        print(f"[Local E2E] Total commands recorded: {len(commands)}")
        for i, cmd in enumerate(commands):
            print(f"[Local E2E]   Command {i + 1}: {cmd}")

        tap_commands = [c for c in commands if c["action"] == "tap"]
        print(f"[Local E2E] Tap commands: {len(tap_commands)} total")
        assert len(tap_commands) == 9, (
            f"Expected 9 tap commands (10 steps - 1 finish), got {len(tap_commands)}. All commands: {commands}"
        )

        # Note: The state machine doesn't transition to 'finished' because finish() is an
        # agent-level action, not a device action. The state machine stays in the last
        # state that was tapped ('back_to_list'). We verify agent completion instead.

        # Verify agent completed successfully
        assert result["success"] is True, "Agent should have completed successfully"
        assert result["steps"] == 10, f"Expected 10 steps, got {result['steps']}"

        print("[Local E2E] ✓ 10-step WeChat test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
