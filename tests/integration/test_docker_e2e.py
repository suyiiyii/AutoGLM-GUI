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
    import platform

    image_name = "autoglm-gui:e2e-test"
    container_name = "autoglm-e2e-test"
    agent_url = mock_agent_server
    host_port = 8000
    is_linux = platform.system() == "Linux"

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

    if is_linux:
        remote_url = agent_url
        docker_args = ["--network", "host"]
        access_url = "http://127.0.0.1:8000"
    else:
        remote_url = agent_url.replace("127.0.0.1", "host.docker.internal")
        docker_args = [
            "--add-host=host.docker.internal:host-gateway",
            "-p",
            f"{host_port}:8000",
        ]
        access_url = f"http://127.0.0.1:{host_port}"

    env = {
        "REMOTE_DEVICE_BASE_URL": remote_url,
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

    yield access_url

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
        docker_container: str,
        test_client: MockAgentTestClient,
        scenario_path: str,
    ):
        """Test complete flow: Docker container -> LLM -> RemoteDevice -> Mock Agent."""
        # Load scenario into mock agent
        test_client.load_scenario(scenario_path)

        # Initialize agent in container
        print(f"[Docker E2E] Initializing agent at {docker_container}")
        resp = httpx.post(
            f"{docker_container}/api/init",
            json={
                "agent_type": "glm",
                "device_id": "mock_device_001",
                "model_config": {
                    "base_url": os.environ["AUTOGLM_BASE_URL"],
                    "api_key": os.environ["AUTOGLM_API_KEY"],
                    "model_name": os.environ["AUTOGLM_MODEL_NAME"],
                },
                "agent_config": {
                    "device_id": "mock_device_001",
                    "max_steps": 10,
                    "verbose": True,
                },
            },
            timeout=30,
        )
        assert resp.status_code == 200
        print(f"[Docker E2E] Init response: {resp.json()}")

        # Send chat request
        instruction = "点击屏幕下方的消息按钮"
        print(f"[Docker E2E] Sending instruction: {instruction}")
        resp = httpx.post(
            f"{docker_container}/api/chat",
            json={
                "device_id": "mock_device_001",
                "message": instruction,
            },
            timeout=120,
        )
        assert resp.status_code == 200

        result = resp.json()
        print(f"[Docker E2E] Chat result: {result}")

        # Assert against mock agent
        print("[Docker E2E] Checking mock agent for recorded commands...")
        commands = test_client.get_commands()
        print(f"[Docker E2E] Total commands recorded: {len(commands)}")

        # Should have at least one tap
        tap_commands = [c for c in commands if c["action"] == "tap"]
        assert len(tap_commands) >= 1, (
            f"Expected at least 1 tap, got {len(tap_commands)}"
        )

        # First tap should be in the message button region
        tap = tap_commands[0]
        x, y = tap["params"]["x"], tap["params"]["y"]
        assert 487 <= x <= 721, f"Tap x={x} not in message button region [487, 721]"
        assert 2516 <= y <= 2667, f"Tap y={y} not in message button region [2516, 2667]"

        # State should have transitioned to "message"
        state = test_client.get_state()
        assert state["current_state"] == "message", (
            f"Expected state 'message', got '{state['current_state']}'"
        )

        print("[Docker E2E] ✓ Test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
