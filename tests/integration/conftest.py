"""Pytest fixtures for integration tests."""

import multiprocessing
import time

import pytest
from pathlib import Path


@pytest.fixture
def scenarios_dir() -> Path:
    """Get the test scenarios directory."""
    return Path(__file__).parent / "fixtures" / "scenarios"


@pytest.fixture
def sample_test_case(scenarios_dir: Path) -> Path:
    """Get the sample test case path (美团外卖测试)."""
    return scenarios_dir / "meituan_message" / "scenario.yaml"


def run_llm_server(port: int):
    """Run the mock LLM server in a subprocess."""
    from tests.integration.device_agent.mock_llm_server import run_server as run_llm

    run_llm(port=port, log_level="warning")


@pytest.fixture(scope="module")
def mock_llm_server():
    """Start mock LLM server for testing."""
    port = 18003
    proc = multiprocessing.Process(target=run_llm_server, args=(port,), daemon=True)
    proc.start()
    time.sleep(1)  # Wait for server startup

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    proc.join(timeout=2)


@pytest.fixture
def mock_llm_client(mock_llm_server: str):
    """Create mock LLM client and reset state."""
    from tests.integration.device_agent.mock_llm_client import MockLLMTestClient

    client = MockLLMTestClient(mock_llm_server)
    client.reset()
    return client
