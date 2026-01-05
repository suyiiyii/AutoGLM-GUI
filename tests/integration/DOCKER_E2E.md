# Docker E2E Testing Guide

This guide explains how to run Docker-based end-to-end integration tests for AutoGLM-GUI using a Mock Device Agent.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Host Machine                              │
│  ┌────────────────┐      ┌─────────────────────┐           │
│  │  pytest        │      │  Mock Device Agent  │           │
│  │  (test runner) │─────>│  (FastAPI Server)   │           │
│  └────────────────┘      │  Port 18001         │           │
│          │               └─────────────────────┘           │
│          │ HTTP                                              │
└──────────┼──────────────────────────────────────────────────┘
           │
           │ HTTP (port 8000)
           ▼
┌─────────────────────────────────────────────────────────────┐
│              Docker Container                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            AutoGLM-GUI (FastAPI)                     │  │
│  │  REMOTE_DEVICE_BASE_URL=http://host.docker.internal │  │
│  │  :18001                                              │  │
│  └────────────────────┬─────────────────────────────────┘  │
│                       │                                      │
│               RemoteDevice (HTTP Client)                   │
└───────────────────────┼──────────────────────────────────────┘
                        │ HTTP (port 18001)
                        ▼
              ┌─────────────────────┐
              │  Mock Device Agent  │
              │  (Records commands) │
              └─────────────────────┘
```

## Prerequisites

1. **Docker**: Install and start Docker
2. **LLM Credentials**: Set environment variables:
   ```bash
   export AUTOGLM_BASE_URL="https://your-llm-api.com/v1"
   export AUTOGLM_MODEL_NAME="your-model-name"
   export AUTOGLM_API_KEY="sk-your-api-key"
   ```

## Running Tests Locally

### Method 1: Direct pytest

```bash
# From project root
cd /Users/suyiiyii/Documents/git/AutoGLM-GUI

# Run Docker E2E tests
uv run pytest tests/integration/test_docker_e2e.py -v -s
```

### Method 2: Manual steps (for debugging)

1. **Start Mock Device Agent**:
   ```bash
   uv run uvicorn tests.integration.device_agent.mock_agent_server:app \
     --host 127.0.0.1 --port 18001
   ```

2. **Build and run Docker container**:
   ```bash
   docker build -t autoglm-gui:e2e-test .
   
   docker run -d \
     --name autoglm-e2e-test \
     --add-host=host.docker.internal:host-gateway \
     -p 8000:8000 \
     -e REMOTE_DEVICE_BASE_URL=http://host.docker.internal:18001 \
     -e AUTOGLM_BASE_URL="$AUTOGLM_BASE_URL" \
     -e AUTOGLM_MODEL_NAME="$AUTOGLM_MODEL_NAME" \
     -e AUTOGLM_API_KEY="$AUTOGLM_API_KEY" \
     autoglm-gui:e2e-test
   ```

3. **Wait for container to be ready**:
   ```bash
   curl http://localhost:8000/api/health
   ```

4. **Run test commands**:
   ```bash
   # Initialize agent
   curl -X POST http://localhost:8000/api/init \
     -H "Content-Type: application/json" \
     -d '{
       "agent_type": "glm",
       "device_id": "mock_device_001",
       "model": {
         "base_url": "'"$AUTOGLM_BASE_URL"'",
         "api_key": "'"$AUTOGLM_API_KEY"'",
         "model_name": "'"$AUTOGLM_MODEL_NAME"'"
       },
       "agent_config": {
         "device_id": "mock_device_001",
         "max_steps": 10
       }
     }'
   
   # Send chat request
   curl -X POST http://localhost:8000/api/chat \
     -H "Content-Type: application/json" \
     -d '{
       "device_id": "mock_device_001",
       "message": "点击屏幕下方的消息按钮"
     }'
   
   # Check mock agent commands
   curl http://localhost:18001/test/commands
   ```

5. **Cleanup**:
   ```bash
   docker stop autoglm-e2e-test
   docker rm autoglm-e2e-test
   ```

## How It Works

### 1. Remote Device Injection

When `REMOTE_DEVICE_BASE_URL` is set, the app automatically injects `RemoteDevice`:

```python
# AutoGLM_GUI/api/__init__.py
def _maybe_inject_remote_device() -> None:
    if remote_base_url := os.getenv("REMOTE_DEVICE_BASE_URL"):
        from AutoGLM_GUI.device_adapter import inject_device_protocol
        from AutoGLM_GUI.devices.remote_device import RemoteDevice

        def get_remote_device(device_id: str | None):
            return RemoteDevice(device_id or "mock_device_001", remote_base_url)

        inject_device_protocol(get_remote_device)
```

### 2. Skip ADB Keyboard in Remote Mode

```python
# AutoGLM_GUI/api/agents.py
def _setup_adb_keyboard(device_id: str) -> None:
    # Skip ADB keyboard setup in remote device mode
    if os.getenv("REMOTE_DEVICE_BASE_URL"):
        logger.info(f"Remote device mode detected, skipping ADB keyboard setup for {device_id}")
        return
    # ... original ADB keyboard setup code
```

### 3. Test Flow

1. **Mock Agent** loads scenario and provides screenshots
2. **Docker Container** receives `/api/chat` request
3. **LLM** processes screenshot + instruction
4. **RemoteDevice** sends tap/swipe commands to Mock Agent via HTTP
5. **Mock Agent** validates coordinates and transitions state machine
6. **pytest** asserts correct commands were received

## Debugging

### View container logs:
```bash
docker logs autoglm-e2e-test -f
```

### Check mock agent state:
```bash
# Current state
curl http://localhost:18001/test/state

# All commands
curl http://localhost:18001/test/commands

# Reset
curl -X POST http://localhost:18001/test/reset
```

### Common issues:

1. **"Connection refused" to mock agent**:
   - Ensure mock agent is running on port 18001
   - Check Docker container can reach `host.docker.internal:18001`

2. **"Container failed to become ready"**:
   - Check Docker logs: `docker logs autoglm-e2e-test`
   - Verify environment variables are set correctly

3. **LLM timeout/failure**:
   - Verify `AUTOGLM_*` credentials are correct
   - Check network connectivity to LLM API

## CI Integration

To add this to GitHub Actions, see `.github/workflows/docker-e2e.yml` (to be created).

Key points:
- Use `ubuntu-latest` runner
- Set `AUTOGLM_*` secrets in GitHub
- No need for `--network host`, use `--add-host=host.docker.internal:host-gateway`

## Next Steps

- Replace real LLM with mock model (future)
- Add more test scenarios
- Convert to nightly builds if LLM calls become expensive/unstable
