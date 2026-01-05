# AGENTS.md

Guide for AI agents working in this codebase.

## Quick Reference

**Python**: `uv run python` (NEVER use raw `python`)  
**Frontend**: `pnpm` in `frontend/` directory  
**DO NOT** modify `phone_agent/` or `mai_agent/` - third-party code

## Configuration System

AutoGLM-GUI uses its own configuration system, independent of `phone_agent` config classes.

### Core Configuration Classes

- `AutoGLM_GUI.config.ModelConfig`: Model API configuration
- `AutoGLM_GUI.config.AgentConfig`: Agent behavior configuration
- `AutoGLM_GUI.config.StepResult`: Execution result type

### Type Conversion

When interfacing with `phone_agent` (e.g., creating PhoneAgent instances),
use `to_phone_agent_config()` methods:

```python
from AutoGLM_GUI.config import ModelConfig, AgentConfig

# Create configs using AutoGLM-GUI types
model_config = ModelConfig(base_url="...", model_name="...")
agent_config = AgentConfig(device_id="...", max_steps=100)

# Convert to phone_agent types (only needed internally in factories)
phone_model = model_config.to_phone_agent_config()
phone_agent = agent_config.to_phone_agent_config()
```

**Important**: Always use `AutoGLM_GUI.config` types in business logic. Only convert to `phone_agent` types at the boundary (e.g., inside agent factories).

## Build / Lint / Test Commands

### Backend (Python)

```bash
uv sync                           # Install dependencies
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload  # Dev server

# Lint
uv run python scripts/lint.py              # Auto-fix (default)
uv run python scripts/lint.py --check-only # Check only (CI)
uv run python scripts/lint.py --backend    # Backend only

# Test
uv run pytest                                              # All tests
uv run pytest tests/test_metrics.py                        # Single file
uv run pytest tests/test_metrics.py::test_metrics_endpoint_available  # Single test
uv run pytest -v -s tests/test_metrics.py                  # Verbose + print
```

### Frontend (TypeScript/React)

```bash
cd frontend
pnpm install        # Install dependencies
pnpm dev            # Dev server (port 3000)
pnpm type-check     # Type check
pnpm lint --fix     # Lint with auto-fix
pnpm format         # Format code
```

## Code Style

### Python (Ruff, Python 3.10+)

```python
# Import order: stdlib -> third-party -> local
import asyncio
from pathlib import Path

from fastapi import FastAPI
from loguru import logger

from AutoGLM_GUI.exceptions import DeviceNotAvailableError
```

**Type hints**: Required for function signatures

```python
def process_device(device_id: str, timeout: float = 5.0) -> dict[str, str]: ...
async def stream_chat(message: str) -> AsyncIterator[dict]: ...
```

**Naming**: `snake_case` (functions/variables), `PascalCase` (classes), `_prefix` (private)

**Logging**: Use centralized loguru logger

```python
from AutoGLM_GUI.logger import logger
logger.info("Message")
logger.exception("Error with traceback")
```

**Exceptions**: Use custom exceptions from `AutoGLM_GUI/exceptions.py`

```python
from AutoGLM_GUI.exceptions import DeviceNotAvailableError
raise DeviceNotAvailableError(f"Device {device_id} offline")
```

### TypeScript/React (ESLint + Prettier)

```typescript
// 2-space indent, single quotes, trailing commas (ES5), semicolons
// Avoid parens for single arrow params

interface DeviceListResponse {
  devices: Device[];
}

export async function listDevices(): Promise<DeviceListResponse> {
  const res = await axios.get<DeviceListResponse>('/api/devices');
  return res.data;
}
```

- Functional components only, TypeScript interfaces for props
- Hooks follow rules-of-hooks (ESLint enforced)

## Critical Constraints

### NEVER Modify Third-Party Code

`phone_agent/` and `mai_agent/` are third-party. For modifications:
1. Use monkey patches in `AutoGLM_GUI/phone_agent_patches.py`
2. Or wrap functionality in `AutoGLM_GUI/` modules

### Type Safety (FORBIDDEN)

- `as any`, `@ts-ignore`, `@ts-expect-error`
- Empty catch blocks `catch(e) {}`

### State Management

Use `PhoneAgentManager` singleton:

```python
from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
manager = PhoneAgentManager.get_instance()
with manager.use_agent(device_id) as agent:
    result = agent.run("Open app")
```

### ADB Commands

Use `platform_utils.py` for cross-platform:

```python
from AutoGLM_GUI.platform_utils import run_command_async
result = await run_command_async(["adb", "devices"])
```

## Testing (pytest)

```python
import pytest
from fastapi.testclient import TestClient
from AutoGLM_GUI.api import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_feature(client):
    response = client.get("/api/endpoint")
    assert response.status_code == 200
```

## Project Structure

```
AutoGLM_GUI/           # Backend - FastAPI app
  api/                 # Route handlers (modular)
  adb_plus/            # Extended ADB utilities
  dual_model/          # Decision + vision model coordination
  exceptions.py        # Custom exceptions
  logger.py            # Loguru config
  phone_agent_manager.py  # Agent lifecycle
  platform_utils.py    # Cross-platform utils

phone_agent/           # Third-party - DO NOT MODIFY
mai_agent/             # Third-party - DO NOT MODIFY

frontend/src/          # React frontend
  routes/              # TanStack Router pages
  components/          # UI components
  api.ts               # API client
```
