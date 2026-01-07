"""Pytest fixtures for integration tests."""

import multiprocessing
import socket
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest


def find_free_port(start: int = 18000, end: int = 19000) -> int:
    """Find a free port in the specified range.

    Args:
        start: Start of port range
        end: End of port range (inclusive)

    Returns:
        A free port number

    Raises:
        RuntimeError: If no free port is found
    """
    for port in range(start, end + 1):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def wait_for_server(url: str, timeout: float = 5.0, endpoint: str = "/test/stats"):
    """Wait for server to become ready.

    Args:
        url: Base URL of the server
        timeout: Maximum wait time in seconds
        endpoint: Health check endpoint

    Raises:
        RuntimeError: If server doesn't become ready within timeout
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(f"{url}{endpoint}", timeout=1.0)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server at {url} failed to start within {timeout}s")


@pytest.fixture
def scenarios_dir() -> Path:
    """Get the test scenarios directory."""
    return Path(__file__).parent / "fixtures" / "scenarios"


@pytest.fixture
def sample_test_case(scenarios_dir: Path) -> Path:
    """Get the sample test case path (美团外卖测试)."""
    return scenarios_dir / "meituan_message" / "scenario.yaml"


def _run_llm_server(port: int):
    """Run the mock LLM server in a subprocess."""
    from tests.integration.device_agent.mock_llm_server import run_server

    run_server(port=port, log_level="warning")


def _run_agent_server(port: int, scenario_path: str | None = None):
    """Run the mock agent server in a subprocess."""
    import uvicorn

    from tests.integration.device_agent.mock_agent_server import create_app

    app = create_app(scenario_path=scenario_path)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture
def mock_llm_server():
    """Start mock LLM server on a free port (function-scoped).

    Returns:
        Base URL of the mock LLM server (e.g., "http://127.0.0.1:18123")

    Example:
        def test_something(mock_llm_server: str):
            model_config = ModelConfig(
                base_url=mock_llm_server + "/v1",
                api_key="mock-key",
                model_name="mock-glm-model"
            )
    """
    port = find_free_port(start=18000, end=18999)
    proc = multiprocessing.Process(target=_run_llm_server, args=(port,), daemon=True)
    proc.start()

    url = f"http://127.0.0.1:{port}"
    wait_for_server(url, timeout=5.0, endpoint="/test/stats")

    yield url

    proc.terminate()
    proc.join(timeout=2)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=1)


@pytest.fixture
def mock_agent_server(request):
    """Start mock agent server on a free port (function-scoped).

    Returns:
        Base URL of the mock agent server (e.g., "http://127.0.0.1:19123")

    Example:
        def test_something(mock_agent_server: str):
            device = RemoteDevice("mock_001", mock_agent_server)
            device.tap(100, 200)

        # With scenario pre-loaded:
        @pytest.mark.parametrize("mock_agent_server", ["path/to/scenario.yaml"], indirect=True)
        def test_with_scenario(mock_agent_server: str):
            # Scenario is already loaded
            pass
    """
    # Check if scenario_path was passed via parametrize
    scenario_path = None
    if hasattr(request, "param"):
        scenario_path = request.param

    port = find_free_port(start=19000, end=19999)
    proc = multiprocessing.Process(
        target=_run_agent_server, args=(port, scenario_path), daemon=True
    )
    proc.start()

    url = f"http://127.0.0.1:{port}"
    wait_for_server(url, timeout=5.0, endpoint="/test/commands")

    yield url

    proc.terminate()
    proc.join(timeout=2)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=1)


@pytest.fixture
def mock_llm_client(mock_llm_server: str):
    """Create mock LLM client and reset state.

    Returns:
        MockLLMTestClient instance with clean state

    Example:
        def test_llm_calls(mock_llm_client):
            # Do something that calls LLM
            agent.run("点击消息按钮")

            # Verify LLM was called
            mock_llm_client.assert_request_count(2)
    """
    from tests.integration.device_agent.mock_llm_client import MockLLMTestClient

    client = MockLLMTestClient(mock_llm_server)
    client.reset()
    return client


@pytest.fixture
def test_client(mock_agent_server: str):
    """Create mock agent test client and reset state.

    Returns:
        MockAgentTestClient instance with clean state

    Example:
        def test_device_commands(test_client):
            device = RemoteDevice("mock_001", mock_agent_server)
            device.tap(100, 200)

            # Verify commands
            test_client.assert_actions(["tap"])
            commands = test_client.get_commands()
            assert commands[0]["params"]["x"] == 100
    """
    from tests.integration.device_agent.test_client import MockAgentTestClient

    client = MockAgentTestClient(mock_agent_server)
    client.reset()
    return client
