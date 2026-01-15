"""Docker-based end-to-end integration tests.

This test module runs AutoGLM-GUI in a Docker container and communicates
with a Mock Device Agent and Mock LLM server running on the host machine.

Prerequisites:
    - Docker is installed and running
"""

import subprocess
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def docker_container(mock_agent_server: str, mock_llm_server: str):
    """Build and run Docker container for testing (function-scoped for isolation).

    Each test gets a fresh container with unique name/tag to ensure reproducibility.
    """
    import uuid

    # Generate unique identifiers for this test run
    test_id = uuid.uuid4().hex[:8]
    image_name = f"autoglm-gui:e2e-test-{test_id}"
    container_name = f"autoglm-e2e-test-{test_id}"

    print(f"\n[Docker E2E] Test ID: {test_id}")
    print(f"[Docker E2E] Image: {image_name}")
    print(f"[Docker E2E] Container: {container_name}")

    # Clean up any existing container with same name (shouldn't exist, but be safe)
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)

    print(f"[Docker E2E] Building Docker image: {image_name}")
    subprocess.run(
        ["docker", "build", "-t", image_name, "."],
        check=True,
        cwd=Path(__file__).parent.parent.parent,
    )

    # Use host network mode for simplicity (works on Linux and macOS with Docker Desktop)
    remote_url = mock_agent_server
    llm_url = mock_llm_server
    docker_args = ["--network", "host"]
    access_url = "http://127.0.0.1:8000"

    print("[Docker E2E] Using host network mode")
    print(f"[Docker E2E] Remote URL: {remote_url}")
    print(f"[Docker E2E] LLM URL: {llm_url}")
    print(f"[Docker E2E] Access URL: {access_url}")

    # Use Mock LLM URL instead of environment variables
    env = {
        "AUTOGLM_BASE_URL": llm_url
        + "/v1",  # Must include /v1 for OpenAI compatibility
        "AUTOGLM_MODEL_NAME": "mock-glm-model",
        "AUTOGLM_API_KEY": "mock-key",
        "AUTOGLM_CORS_ORIGINS": "*",
        "HOME": "/tmp",  # Override HOME to avoid loading user config
    }

    env_list = []
    for k, v in env.items():
        env_list.extend(["-e", f"{k}={v}"])

    print(f"[Docker E2E] Starting container: {container_name}")
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            *docker_args,
            *env_list,
            image_name,
        ],
        check=True,
    )

    print("[Docker E2E] Waiting for container to start...")
    for i in range(30):
        try:
            resp = httpx.get(f"{access_url}/api/health", timeout=2)
            if resp.status_code == 200:
                print("[Docker E2E] Container is ready!")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Container failed to become ready")

    yield {
        "access_url": access_url,
        "remote_url": remote_url,
        "llm_url": llm_url,
        "image_name": image_name,
        "container_name": container_name,
    }

    # Cleanup: Stop and remove container
    print(f"[Docker E2E] Stopping container: {container_name}")
    subprocess.run(
        ["docker", "stop", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["docker", "rm", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Cleanup: Remove image
    print(f"[Docker E2E] Removing image: {image_name}")
    subprocess.run(
        ["docker", "rmi", image_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class TestDockerE2E:
    """End-to-end tests with AutoGLM-GUI running in Docker."""

    def test_meituan_message_scenario(
        self,
        docker_container: dict,
        mock_llm_client,
        test_client,
        sample_test_case,
    ):
        """Test complete flow: Docker container -> Mock LLM -> RemoteDevice -> Mock Agent."""
        access_url = docker_container["access_url"]
        remote_url = docker_container["remote_url"]
        llm_url = docker_container["llm_url"]

        test_client.load_scenario(str(sample_test_case))

        print(f"[Docker E2E] Registering remote device at {access_url}")
        print(f"[Docker E2E] Remote URL: {remote_url}")

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
                            f"[Docker E2E] Cleaned up existing device {device_id}: {resp.status_code}"
                        )
        except Exception as e:
            print(f"[Docker E2E] Failed to cleanup devices: {e}")

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
        print(f"[Docker E2E] Device registered: {register_result}")

        if not register_result["success"]:
            error_msg = register_result.get("message", "Unknown error")
            print(f"[Docker E2E] ERROR: Remote device registration failed: {error_msg}")

            # Provide troubleshooting hints
            if "nodename nor servname provided" in error_msg or "Errno 8" in error_msg:
                print("[Docker E2E] ")
                print("[Docker E2E] DNS Resolution Error - Troubleshooting:")
                print(
                    f"[Docker E2E]   1. Check if mock agent is running: curl {remote_url}/health"
                )
                print(
                    f"[Docker E2E]   2. Test from container: docker exec autoglm-e2e-test curl {remote_url}/health"
                )
                print(
                    "[Docker E2E]   3. Verify Docker Desktop supports host.docker.internal"
                )
                print(
                    "[Docker E2E]   4. Try: docker run --add-host=host.docker.internal:host-gateway ..."
                )
                print("[Docker E2E] ")

            pytest.fail(f"Remote device registration failed: {error_msg}")

        registered_serial = register_result["serial"]
        print(f"[Docker E2E] Registered device serial: {registered_serial}")

        print(f"[Docker E2E] Verifying device discovery at {access_url}")
        resp = httpx.get(f"{access_url}/api/devices", timeout=10)
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        print(f"[Docker E2E] Found {len(devices)} device(s): {devices}")

        # Find the remote device we just registered
        remote_devices = [d for d in devices if d["serial"] == registered_serial]
        assert len(remote_devices) > 0, (
            f"Registered remote device {registered_serial} not found in device list. "
            f"Available devices: {[d['serial'] for d in devices]}"
        )

        registered_device_id = remote_devices[0]["id"]
        print(f"[Docker E2E] Using remote device_id: {registered_device_id}")

        print(f"[Docker E2E] Initializing agent at {access_url}")
        print(f"[Docker E2E] Using Mock LLM at: {llm_url}")

        # Delete existing config file to use environment variables
        try:
            resp = httpx.delete(f"{access_url}/api/config", timeout=10)
            print(f"[Docker E2E] Deleted existing config: {resp.status_code}")
        except Exception as e:
            print(f"[Docker E2E] No config to delete: {e}")

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
        print(f"[Docker E2E] Saved new config: {resp.json()}")

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
            print(f"[Docker E2E] ERROR: Init failed with status {resp.status_code}")
            print(f"[Docker E2E] Response: {resp.text}")
        assert resp.status_code == 200, f"Init failed: {resp.text}"
        print(f"[Docker E2E] Init response: {resp.json()}")

        instruction = "点击屏幕下方的消息按钮"
        print(f"[Docker E2E] Sending instruction: {instruction}")
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
        print(f"[Docker E2E] Chat result: {result}")

        # Verify Mock LLM was called
        print("[Docker E2E] Verifying Mock LLM calls...")
        mock_llm_stats = mock_llm_client.get_stats()
        print(f"[Docker E2E] Mock LLM request count: {mock_llm_stats['request_count']}")
        assert mock_llm_stats["request_count"] == 2, (
            f"Expected 2 LLM requests, got {mock_llm_stats['request_count']}"
        )

        print("[Docker E2E] Checking mock agent for recorded commands...")
        commands = test_client.get_commands()
        print(f"[Docker E2E] Total commands recorded: {len(commands)}")
        for i, cmd in enumerate(commands):
            print(f"[Docker E2E]   Command {i + 1}: {cmd}")

        tap_commands = [c for c in commands if c["action"] == "tap"]
        print(f"[Docker E2E] Tap commands: {tap_commands}")
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

        print("[Docker E2E] ✓ Test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
