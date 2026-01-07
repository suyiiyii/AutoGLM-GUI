# Integration Test Fixtures Guide

## Overview

This guide explains how to use the Mock Server fixtures in `conftest.py` for integration testing.

## Key Features

✅ **Automatic Port Allocation**: Finds free ports in the 18000-19999 range
✅ **Function-Scoped**: Each test gets fresh server instances
✅ **Auto Cleanup**: Processes are terminated and killed after test completion
✅ **Health Checks**: Waits for servers to become ready before yielding
✅ **Zero Configuration**: Just declare fixtures in test parameters

---

## Available Fixtures

### 1. `mock_llm_server` - Mock LLM Server

Returns the base URL of a mock OpenAI-compatible LLM server.

**Scope**: Function (new instance per test)
**Port Range**: 18000-18999
**Health Endpoint**: `/test/stats`

**Example**:
```python
def test_with_mock_llm(mock_llm_server: str):
    model_config = ModelConfig(
        base_url=mock_llm_server + "/v1",
        api_key="mock-key",
        model_name="mock-glm-model"
    )
    # Use model_config in your test
```

---

### 2. `mock_agent_server` - Mock Device Agent Server

Returns the base URL of a mock device agent server.

**Scope**: Function (new instance per test)
**Port Range**: 19000-19999
**Health Endpoint**: `/test/commands`

**Example**:
```python
def test_with_mock_agent(mock_agent_server: str):
    device = RemoteDevice("mock_001", mock_agent_server)
    device.tap(100, 200)
```

**With Pre-loaded Scenario** (Advanced):
```python
@pytest.mark.parametrize(
    "mock_agent_server",
    ["path/to/scenario.yaml"],
    indirect=True
)
def test_with_scenario(mock_agent_server: str):
    # Scenario is already loaded in the server
    device = RemoteDevice("mock_001", mock_agent_server)
    device.tap(100, 200)
```

---

### 3. `mock_llm_client` - Mock LLM Test Client

Returns a `MockLLMTestClient` instance with clean state.

**Depends on**: `mock_llm_server`
**Auto Reset**: Yes (calls `reset()` before yielding)

**Example**:
```python
def test_llm_calls(mock_llm_client):
    # Do something that calls LLM
    agent.run("点击消息按钮")

    # Verify LLM was called
    mock_llm_client.assert_request_count(2)
    stats = mock_llm_client.get_stats()
```

---

### 4. `test_client` - Mock Agent Test Client

Returns a `MockAgentTestClient` instance with clean state.

**Depends on**: `mock_agent_server`
**Auto Reset**: Yes (calls `reset()` before yielding)

**Example**:
```python
def test_device_commands(test_client, mock_agent_server: str):
    device = RemoteDevice("mock_001", mock_agent_server)
    device.tap(100, 200)

    # Verify commands
    test_client.assert_actions(["tap"])
    commands = test_client.get_commands()
    assert commands[0]["params"]["x"] == 100
```

---

### 5. `sample_test_case` - Sample Scenario Path

Returns the path to the "美团外卖消息" test scenario.

**Returns**: `Path` object
**Scope**: Function

**Example**:
```python
def test_with_scenario(test_client, sample_test_case):
    test_client.load_scenario(str(sample_test_case))
    # Now the mock agent has state machine loaded
```

---

## Complete Examples

### Example 1: Basic Device Command Test

```python
def test_tap_records_command(mock_agent_server: str, test_client):
    """Test that tap is recorded by mock agent."""
    device = RemoteDevice("mock_001", mock_agent_server)

    device.tap(100, 200)

    commands = test_client.get_actions()
    assert len(commands) == 1
    assert commands[0]["action"] == "tap"
    assert commands[0]["x"] == 100
    assert commands[0]["y"] == 200
```

### Example 2: Agent with Mock LLM

```python
def test_agent_with_mock_llm(
    mock_llm_server: str,
    mock_agent_server: str,
    mock_llm_client,
    test_client,
    sample_test_case
):
    """Test agent with mock LLM and mock device - no credentials required."""
    from AutoGLM_GUI.agents.glm.agent import GLMAgent
    from AutoGLM_GUI.config import AgentConfig, ModelConfig
    from AutoGLM_GUI.devices.remote_device import RemoteDevice

    # Load test scenario
    test_client.load_scenario(str(sample_test_case))

    # Configure mock LLM (no real credentials needed!)
    model_config = ModelConfig(
        base_url=mock_llm_server + "/v1",
        api_key="mock-key",
        model_name="mock-glm-model"
    )

    agent_config = AgentConfig(
        max_steps=5,
        device_id="mock_device_001",
        verbose=True
    )

    # Create remote device
    remote_device = RemoteDevice("mock_device_001", mock_agent_server)

    # Run agent
    with DeviceProtocolContext(
        get_device=lambda _: remote_device,
        default_device_id="mock_device_001"
    ):
        agent = GLMAgent(
            model_config=model_config,
            agent_config=agent_config,
            device=remote_device
        )
        agent.run("点击屏幕下方的消息按钮")

    # Verify mock LLM was called twice (tap + finish)
    mock_llm_client.assert_request_count(2)

    # Verify device received tap command
    test_client.assert_tap_in_region(487, 2516, 721, 2667)
    test_client.assert_state("message")
```

### Example 3: Parallel Tests with Independent Servers

```python
# Test 1 - Gets mock_llm_server on port 18234
def test_one(mock_llm_server: str):
    assert "http://127.0.0.1" in mock_llm_server
    # Do test work

# Test 2 - Gets DIFFERENT mock_llm_server on port 18567
def test_two(mock_llm_server: str):
    assert "http://127.0.0.1" in mock_llm_server
    # Do test work
```

These tests can run in parallel because each gets its own server instance on a different port!

---

## Migration Guide

### Before (Old Pattern)

```python
import multiprocessing
import time

def run_server(port: int):
    from tests.integration.device_agent.mock_llm_server import run_server
    run_server(port=port, log_level="warning")

@pytest.fixture(scope="module")
def mock_llm_server():
    port = 18003
    proc = multiprocessing.Process(target=run_server, args=(port,), daemon=True)
    proc.start()
    time.sleep(2)

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    proc.join(timeout=2)
```

### After (New Pattern)

```python
# No fixture definition needed! Just use it:
def test_something(mock_llm_server: str):
    # Fixture is already defined in conftest.py
    pass
```

---

## Technical Details

### Port Allocation Algorithm

```python
def find_free_port(start: int = 18000, end: int = 19000) -> int:
    """Find a free port by trying to bind to each port in range."""
    for port in range(start, end + 1):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")
```

### Health Check Mechanism

```python
def wait_for_server(url: str, timeout: float = 5.0, endpoint: str = "/test/stats"):
    """Poll server until it responds with 200 OK."""
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
```

### Cleanup Process

```python
# Graceful shutdown with fallback to force kill
proc.terminate()  # Send SIGTERM
proc.join(timeout=2)  # Wait up to 2 seconds
if proc.is_alive():
    proc.kill()  # Force kill if still alive
    proc.join(timeout=1)
```

---

## Troubleshooting

### Problem: Port Already in Use

**Symptom**: `RuntimeError: No free port found in range 18000-19000`

**Solution**: The fixture will automatically find a free port. If you still see this error, check if you have too many zombie processes:

```bash
# macOS/Linux
lsof -i :18000-19000 | grep python
kill -9 <PID>

# Or use the cleanup script
pkill -f "mock_llm_server|mock_agent_server"
```

### Problem: Server Fails to Start

**Symptom**: `RuntimeError: Server at http://127.0.0.1:18123 failed to start within 5.0s`

**Solution**: Check server logs. The fixture uses `log_level="warning"` by default. To debug:

1. Check if dependencies are installed: `uv sync`
2. Run server manually: `uv run python tests/integration/device_agent/mock_llm_server.py`
3. Check if port is blocked by firewall

### Problem: Tests Hang

**Symptom**: Test hangs indefinitely, never completes

**Solution**: Check if process cleanup is working:

```bash
# Check for zombie processes
ps aux | grep pytest
ps aux | grep mock_

# Force cleanup
pkill -f pytest
```

### Problem: Fixture Not Found

**Symptom**: `fixture 'mock_llm_server' not found`

**Solution**: Ensure `conftest.py` is in the correct location:

```
tests/integration/
├── conftest.py          # ← Fixtures defined here
├── test_agent_integration.py
└── device_agent/
    ├── test_remote_device.py
    └── test_e2e_with_adapter.py
```

pytest automatically discovers `conftest.py` in parent directories.

---

## Best Practices

1. **Use Function Scope**: Always use function-scoped fixtures (default) for isolated tests
2. **Avoid Hardcoded Ports**: Never hardcode ports - let the fixture find free ones
3. **Don't Share Servers**: Each test should get its own server instances
4. **Reset State**: Always reset client state between tests (done automatically by `mock_llm_client` and `test_client`)
5. **Keep Tests Fast**: Function-scoped fixtures are fast (~100ms startup)
6. **Use Type Hints**: Always annotate fixture types for better IDE support

---

## Performance

**Fixture Startup Times** (measured on macOS M1):

| Fixture | Startup Time | Notes |
|---------|--------------|-------|
| `mock_llm_server` | ~100ms | Port finding + health check |
| `mock_agent_server` | ~150ms | Port finding + uvicorn startup |
| `mock_llm_client` | ~10ms | HTTP client creation |
| `test_client` | ~10ms | HTTP client creation |

**Total Test Overhead**: ~200-300ms per test (still very fast!)

---

## See Also

- `mock_llm_server.py` - Mock LLM server implementation
- `mock_agent_server.py` - Mock device agent server implementation
- `mock_llm_client.py` - Mock LLM test client
- `test_client.py` - Mock agent test client
