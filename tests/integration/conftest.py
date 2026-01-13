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


# ============================================================================
# SSE (Server-Sent Events) Fixtures for Streaming Tests
# ============================================================================


class SSEEvent:
    """Represents a parsed SSE event."""

    def __init__(
        self, data: str, event_type: str = "message", event_id: str | None = None
    ):
        """Initialize SSE event.

        Args:
            data: Event data payload
            event_type: Event type (default: "message")
            event_id: Optional event ID
        """
        self.data = data
        self.event_type = event_type
        self.event_id = event_id

    def to_dict(self) -> dict:
        """Convert event to dictionary representation."""
        result = {"type": self.event_type, "data": self.data}
        if self.event_id is not None:
            result["id"] = self.event_id
        return result


class SSEEventParser:
    """Parser for Server-Sent Events (SSE) from streaming responses.

    Parses SSE format:
        data: {"key": "value"}
        event: step
        id: 1

    Used for testing:
        - /api/chat/stream (classic agent)
        - /api/layered-agent/chat (layered agent)
    """

    def __init__(self):
        """Initialize SSE parser."""
        self.events: list[SSEEvent] = []
        self.buffer: str = ""

    def parse_response(self, response) -> list[dict]:
        """Parse SSE response into list of event dicts.

        Args:
            response: HTTP response object with iter_lines() method

        Returns:
            List of event dictionaries with keys: type, data, id (optional)
        """
        self.events = []
        self.buffer = ""

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                self._flush_buffer()
                continue

            if line.startswith("data:"):
                data = line[5:].strip()
                self._append_to_buffer("data", data)
            elif line.startswith("event:"):
                event_type = line[6:].strip()
                self._append_to_buffer("event", event_type)
            elif line.startswith("id:"):
                event_id = line[3:].strip()
                self._append_to_buffer("id", event_id)

        # Flush any remaining data
        self._flush_buffer()

        return [event.to_dict() for event in self.events]

    def _append_to_buffer(self, key: str, value: str) -> None:
        """Append key-value to buffer."""
        if self.buffer:
            self.buffer += ";"
        self.buffer += f"{key}:{value}"

    def _flush_buffer(self) -> None:
        """Flush buffer and create event."""
        if not self.buffer:
            return

        data = None
        event_type = "message"
        event_id = None

        for part in self.buffer.split(";"):
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            key = key.strip()
            value = value.strip()

            if key == "data":
                data = value
            elif key == "event":
                event_type = value
            elif key == "id":
                event_id = value

        if data is not None:
            self.events.append(SSEEvent(data, event_type, event_id))

        self.buffer = ""


@pytest.fixture
def sse_event_parser():
    """SSE event parser fixture for testing streaming endpoints.

    Returns:
        SSEEventParser instance for parsing SSE streams

    Example:
        def test_sse_stream(client, sse_event_parser):
            response = client.post("/api/chat/stream", json={...})
            events = sse_event_parser.parse_response(response)

            # Verify event types
            event_types = [e["type"] for e in events]
            assert "thinking_chunk" in event_types
            assert "step" in event_types
            assert "done" in event_types
    """
    return SSEEventParser()


# ============================================================================
# Multi-Device Pool Fixture for Concurrency Tests
# ============================================================================


@pytest.fixture
def multi_device_pool():
    """Multi-device mock server pool for concurrency testing.

    Creates 3 mock device servers with independent ports.
    Each device has its own RemoteDevice instance.

    Returns:
        List of (device_id, server_url, RemoteDevice) tuples

    Example:
        def test_multi_device_operations(multi_device_pool):
            device_1_id, device_1_url, device_1 = multi_device_pool[0]
            device_2_id, device_2_url, device_2 = multi_device_pool[1]

            # Operate on both devices
            device_1.tap(100, 200)
            device_2.tap(300, 400)
    """
    from AutoGLM_GUI.devices.remote_device import RemoteDevice

    devices = []
    procs = []

    try:
        for i in range(3):
            port = find_free_port(start=19000 + i * 100, end=19100 + i * 100)
            proc = multiprocessing.Process(
                target=_run_agent_server, args=(port, None), daemon=True
            )
            proc.start()
            procs.append(proc)

            url = f"http://127.0.0.1:{port}"
            wait_for_server(url, timeout=5.0, endpoint="/test/commands")

            device_id = f"mock_device_{i:03d}"
            device = RemoteDevice(device_id, url)
            devices.append((device_id, url, device))

        yield devices

    finally:
        # Cleanup: terminate all processes
        for proc in procs:
            proc.terminate()
            proc.join(timeout=2)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1)


# ============================================================================
# FastAPI Test Client Fixture
# ============================================================================


@pytest.fixture
def api_client():
    """Create FastAPI TestClient for backend E2E tests.

    Returns:
        TestClient instance for making HTTP requests to FastAPI app

    Example:
        def test_api_endpoint(api_client):
            response = api_client.get("/api/devices")
            assert response.status_code == 200
    """
    from fastapi.testclient import TestClient
    from AutoGLM_GUI.api import create_app

    app = create_app()
    return TestClient(app)
