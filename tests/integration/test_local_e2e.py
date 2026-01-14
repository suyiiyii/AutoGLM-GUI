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
        assert 487 <= x <= 721, f"Tap x={x} not in message button region [487, 721]"
        assert 2516 <= y <= 2667, f"Tap y={y} not in message button region [2516, 2667]"

        state = test_client.get_state()
        assert state["current_state"] == "message", (
            f"Expected state 'message', got '{state['current_state']}'"
        )

        print("[Local E2E] ✓ Test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
