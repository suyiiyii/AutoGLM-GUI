"""Docker-based end-to-end integration tests.

This test module runs AutoGLM-GUI in a Docker container and communicates
with a Mock Device Agent running on the host machine.

Prerequisites:
    - Docker is installed and running
    - AUTOGLM_BASE_URL, AUTOGLM_MODEL_NAME, AUTOGLM_API_KEY are set
"""

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests.integration.device_agent.test_client import MockAgentTestClient


@pytest.fixture(scope="module")
def mock_agent_server():
    """Start mock agent server on host machine."""
    port = 18001

    try:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "tests.integration.device_agent.mock_agent_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=Path(__file__).parent.parent.parent,
    )
    time.sleep(2)

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    proc.wait(timeout=5)


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
        Path(__file__).parent
        / "fixtures"
        / "scenarios"
        / "meituan_message"
        / "scenario.yaml"
    )


def has_llm_config() -> bool:
    """Check if LLM config is available."""
    return bool(
        os.environ.get("AUTOGLM_BASE_URL")
        and os.environ.get("AUTOGLM_API_KEY")
        and os.environ.get("AUTOGLM_MODEL_NAME")
    )


@pytest.fixture(scope="module")
def docker_container(mock_agent_server: str):
    """Build and run Docker container for testing."""
    image_name = "autoglm-gui:e2e-test"
    container_name = "autoglm-e2e-test"

    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
    )
    time.sleep(0.5)

    print(f"\n[Docker E2E] Building Docker image: {image_name}")
    subprocess.run(
        ["docker", "build", "-t", image_name, "."],
        check=True,
        cwd=Path(__file__).parent.parent.parent,
    )

    # Use host network mode for simplicity (works on Linux and macOS with Docker Desktop)
    remote_url = mock_agent_server
    docker_args = ["--network", "host"]
    access_url = "http://127.0.0.1:8000"

    print("[Docker E2E] Using host network mode")
    print(f"[Docker E2E] Remote URL: {remote_url}")
    print(f"[Docker E2E] Access URL: {access_url}")

    # No longer use REMOTE_DEVICE_BASE_URL - devices are registered via API instead
    env = {
        "AUTOGLM_BASE_URL": os.environ.get("AUTOGLM_BASE_URL", ""),
        "AUTOGLM_MODEL_NAME": os.environ.get("AUTOGLM_MODEL_NAME", ""),
        "AUTOGLM_API_KEY": os.environ.get("AUTOGLM_API_KEY", ""),
        "AUTOGLM_CORS_ORIGINS": "*",
    }

    env_list = []
    for k, v in env.items():
        if v:
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

    yield {"access_url": access_url, "remote_url": remote_url}

    print(f"[Docker E2E] Stopping container: {container_name}")
    subprocess.run(["docker", "stop", container_name], capture_output=True)
    subprocess.run(["docker", "rm", container_name], capture_output=True)


@pytest.mark.skipif(
    not has_llm_config(), reason="LLM config not available (set AUTOGLM_* env vars)"
)
class TestDockerE2E:
    """End-to-end tests with AutoGLM-GUI running in Docker."""

    def test_meituan_message_scenario(
        self,
        docker_container: dict,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test complete flow: Docker container -> LLM -> RemoteDevice -> Mock Agent."""
        access_url = docker_container["access_url"]
        remote_url = docker_container["remote_url"]

        test_client.load_scenario(scenario_path)

        print(f"[Docker E2E] Registering remote device at {access_url}")
        print(f"[Docker E2E] Remote URL: {remote_url}")
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
                    f"[Docker E2E]   1. Check if mock agent is running: curl {mock_agent_server}/health"
                )
                print(
                    f"[Docker E2E]   2. Test from container: docker exec autoglm-e2e-test curl {remote_url}/health"
                )
                print("[Docker E2E]   3. Verify Docker Desktop supports host.docker.internal")
                print("[Docker E2E]   4. Try: docker run --add-host=host.docker.internal:host-gateway ...")
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
        resp = httpx.post(
            f"{access_url}/api/init",
            json={
                "agent_type": "glm",
                "device_id": registered_device_id,
                "model_config": {
                    "base_url": os.environ["AUTOGLM_BASE_URL"],
                    "api_key": os.environ["AUTOGLM_API_KEY"],
                    "model_name": os.environ["AUTOGLM_MODEL_NAME"],
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
