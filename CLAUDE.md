# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture overview

AutoGLM-GUI is an AI-driven Android automation platform. A Python FastAPI backend controls Android devices via ADB and exposes REST / Socket.IO / MCP APIs. A React 19 + TypeScript frontend (TanStack Router, Tailwind CSS 4, Radix UI) provides the GUI. An Electron wrapper packages it as a desktop app.

### Server composition

[server.py](AutoGLM_GUI/server.py) wraps FastAPI inside a Socket.IO `ASGIApp`. The FastAPI app is built in [api/__init__.py](AutoGLM_GUI/api/__init__.py) (`create_app()`), which composes three ASGI layers by mount order:

1. `/assets` — Vite-built hashed frontend assets (long cache, deterministic MIME via `_FrontendStaticFiles`)
2. `/mcp*` — FastMCP HTTP+SSE app (delegated from the SPA handler)
3. `/*` — SPA fallback: serves static files if they exist, otherwise `index.html` (no cache)

All 12 API routers are registered on the FastAPI app: `agents`, `control`, `devices`, `health`, `history`, `layered_agent`, `media`, `metrics`, `scheduled_tasks`, `tasks`, `terminal`, `version`, `workflows`.

### Agent system

**Protocol**: [agents/protocols.py](AutoGLM_GUI/agents/protocols.py) — `AsyncAgent` defines the async streaming contract: `stream(task) -> AsyncIterator[dict]`. Event types: `thinking` (streaming chunks), `step` (one step complete), `done`, `cancelled`, `error`. Cancel uses `asyncio.CancelledError` to kill in-flight HTTP requests instantly — no worker threads or queues.

**Factory + registry**: [agents/factory.py](AutoGLM_GUI/agents/factory.py). `register_agent(type, creator)` → `create_agent(type, model_config, agent_config, agent_specific_config, device, ...)`. Built-in agent types:

| Type | Module | Description |
|------|--------|-------------|
| `glm-async` / `async-glm` | `agents/glm/` | GLM vision model (default). `<answer>` tag parsing, AST-based action extraction |
| `qwen` | `agents/qwen/` | Qwen3.6 agent. `<thought>/<answer>` format, AST-based parser with bracket repair, `info()` action |
| `mai` | `agents/mai/` | Mobile Agent with trajectory memory (`history_n` param, 1-10). Multi-screenshot context for complex tasks |
| `gemini` / `general-vision` | `agents/gemini/` | OpenAI-compatible function calling for general vision models (Gemini, GPT-4o, Claude) |
| `droidrun` | `agents/droidrun/` | Wraps DroidRun's DroidAgent. Manages its own ADB connection; needs Portal APK |
| `midscene` | `agents/midscene/` | Wraps Midscene.js CLI. Requires Node.js/npx in PATH |

Each agent type stores its specific config as `AgentSpecificConfig` (typed dict, [types.py](AutoGLM_GUI/types.py)), passed through the factory.

Each agent has per-language prompts (`prompts_zh.py` / `prompts_en.py` for GLM and Qwen; `prompts.py` for MAI).

### Device abstraction

[device_protocol.py](AutoGLM_GUI/device_protocol.py) defines `DeviceProtocol` — the stable interface agents code against: `get_screenshot()`, `tap(x,y)`, `swipe(...)`, `type_text()`, `launch_app()`, `back()`, `home()`, `get_current_app()`, `detect_and_set_adb_keyboard()`, `restore_keyboard()`.

Three implementations in [devices/](AutoGLM_GUI/devices/):
- `ADBDevice` — real devices via `adb shell` subprocess calls
- `RemoteDevice` — remote agent via HTTP
- `MockDevice` — test state machine (used in integration tests)

Agents receive a `DeviceProtocol` at construction — they never call ADB directly.

### Core singleton managers

- **`DeviceManager`** ([device_manager.py](AutoGLM_GUI/device_manager.py)): Device discovery with background polling via `ThreadPoolExecutor`. Connection lifecycle (USB, WiFi, remote). Returns `DeviceProtocol` instances. Uses three identifier vocabularies: `DeviceSerial` (canonical), `ConnectionDeviceID` (transport endpoint), `PrimaryDeviceID` (currently selected).
- **`PhoneAgentManager`** ([phone_agent_manager.py](AutoGLM_GUI/phone_agent_manager.py)): Per-device agent lifecycle. State machine: `IDLE ↔ BUSY` (atomic transitions), `ERROR`, `INITIALIZING`. Thread-safe device-level locks enforce single-task-per-device concurrency. `use_agent(device_id)` context manager auto-acquires/releases locks.
- **`SchedulerManager`** ([scheduler_manager.py](AutoGLM_GUI/scheduler_manager.py)): APScheduler-backed cron scheduler. Runs scheduled workflow tasks against specified devices.
- **`TaskManager`** ([task_manager.py](AutoGLM_GUI/task_manager.py)): Queue-backed task orchestrator with per-device workers. Registers executors for `classic_chat`, `layered_chat`, `scheduled_workflow`, `scheduled_layered_workflow`.
- **`config_manager`** ([config_manager.py](AutoGLM_GUI/config_manager.py)): See config system below.
- **`WorkflowManager`** ([workflow_manager.py](AutoGLM_GUI/workflow_manager.py)): Singleton, JSON-file persistence, mtime-based caching, atomic writes.

### Config system

[config_manager.py](AutoGLM_GUI/config_manager.py): Four-layer priority — **CLI args > env vars > config file (~/.config/autoglm/config.json) > defaults**. Pydantic `ConfigModel` with validation. Tracks source per field (`ConfigSource` enum). Supports hot-reload via mtime caching and config-hash change detection.

Two model config targets:
- **Vision model**: `base_url`, `model_name`, `api_key` — for the phone agent
- **Decision model**: `decision_base_url`, `decision_model_name`, `decision_api_key` — for the layered planner

Env vars: `AUTOGLM_BASE_URL`, `AUTOGLM_MODEL_NAME`, `AUTOGLM_API_KEY`, `AUTOGLM_ADB_PATH`, `AUTOGLM_LOG_LEVEL`, `AUTOGLM_CORS_ORIGINS`, `AUTOGLM_TRACE_ENABLED`, `AUTOGLM_TRACE_FILE`.

### Layered agent

[layered_agent_service.py](AutoGLM_GUI/layered_agent_service.py) + [api/layered_agent.py](AutoGLM_GUI/api/layered_agent.py): Two-tier architecture using OpenAI Agent SDK:

```
User → Planner (decision model, e.g. GPT/Claude) → tools → Executor (vision model) → ADB → Device
```

Planner tools: `list_devices()` returns device list, `chat(device_id, message)` calls `PhoneAgentManager.use_agent()` to run the vision model. Each `chat` call is capped at `MCP_MAX_STEPS=5` — the planner must decompose complex tasks into atomic sub-tasks. Planner uses `SQLiteSession` for cross-turn memory. Active runs tracked in `_active_runs` dict with `threading.Lock`, cancelable via `result.cancel(mode="immediate")`.

Planner instructions (`PLANNER_INSTRUCTIONS`) encode the executor's limitations: no memory/note function, no system-level access, no clipboard access. The planner must ask the executor to "read" screen content aloud rather than expecting structured data extraction.

SSE events emitted: `tool_call`, `tool_result`, `message`, `done`, `error`.

### Video streaming (scrcpy)

[scrcpy_stream.py](AutoGLM_GUI/scrcpy_stream.py): Launches scrcpy-server as a subprocess, parses the ya-webadb-aligned media stream protocol. [scrcpy_protocol.py](AutoGLM_GUI/scrcpy_protocol.py) handles binary packet parsing (codec negotiation, PTS handling).

[socketio_server.py](AutoGLM_GUI/socketio_server.py): Socket.IO `AsyncServer` relays video packets to web clients. Per-device `ScrcpyStreamer` instances, per-SID stream tasks, device-level `asyncio.Lock` to prevent concurrent stream connections.

### Action system

[actions/handler.py](AutoGLM_GUI/actions/handler.py): `ActionHandler` executes parsed actions against a `DeviceProtocol`. Supports: `tap`, `swipe`, `type`, `long_press`, `double_tap`, `back`, `home`, `launch`, `finish`, `wait`, `take_over`, `confirm`, `call_api`, `interact`. Each action is traced via `trace_span`. Coordinates are normalized using screen dimensions.

### Tracing

[trace.py](AutoGLM_GUI/trace.py): Contextvar-based span tree. Enabled by default (`AUTOGLM_TRACE_ENABLED`). Spans written as JSONL to `logs/trace_{date}.jsonl`. Each task gets a `trace_id` stored in `task_runs.trace_id` — filter the JSONL by this value to inspect a single task.

Span coverage: `model.call`, `step.llm`, `action.execute`, `adb.*`, `device.*`, `tool.call`/`tool.result`, `memory.read`/`memory.write`, `task_store.*`, `history.*`, `layered.planner.*`.

Step timing fields tracked: `total_duration_ms`, `screenshot_duration_ms`, `llm_duration_ms`, `parse_action_duration_ms`, `execute_action_duration_ms`, `adb_duration_ms`, `sleep_duration_ms`.

Prometheus metrics ([metrics.py](AutoGLM_GUI/metrics.py)) exposed at `/api/metrics` aggregate task latency histograms from trace data.

### Data models

- [models/scheduled_task.py](AutoGLM_GUI/models/scheduled_task.py): `ScheduledTask` dataclass with cron expression, workflow binding, device serialnos, execution mode, last-run tracking. JSON-serializable via `to_dict`/`from_dict`.
- [models/history.py](AutoGLM_GUI/models/history.py): History records for conversation persistence.
- [models/device_group.py](AutoGLM_GUI/models/device_group.py): Device group model for batch operations.

### Frontend architecture

```
frontend/src/
├── main.tsx                  # React entry point
├── routeTree.gen.ts          # Auto-generated TanStack Router tree
├── routes/                   # Page-level components
│   ├── __root.tsx            # Root layout + navigation sidebar
│   ├── chat.tsx              # Main chat/device control interface
│   ├── workflows.tsx         # Workflow management page
│   ├── scheduled-tasks.tsx   # Cron task management
│   ├── history.tsx           # Conversation history browser
│   ├── terminal.tsx          # ADB terminal page
│   ├── logs.tsx              # Log viewer
│   ├── about.tsx             # About page
│   └── index.tsx             # Landing/redirect
├── components/
│   ├── ChatKitPanel.tsx      # Chat interface (messages, input, workflow selector)
│   ├── ScrcpyPlayer.tsx      # Video player using WebCodecs
│   ├── DevicePanel.tsx       # Device control + video display
│   ├── DeviceSidebar.tsx     # Device list sidebar
│   ├── GroupedDeviceList.tsx # Grouped device list with drag-and-drop
│   ├── NavigationSidebar.tsx # Main navigation
│   └── ui/                   # Radix UI primitives (button, dialog, select, etc.)
├── lib/
│   ├── sse.ts                # SSE client for streaming API responses
│   ├── webcodecs-utils.ts    # WebCodecs video decoding utilities
│   ├── i18n.ts + i18n-context.tsx  # Internationalization (zh/en)
│   ├── theme-provider.tsx    # Dark/light theme
│   └── locales/en.ts, zh.ts # Translation strings
├── hooks/                    # Custom React hooks
│   ├── useTaskSessionConversation.ts  # Task + chat state management
│   ├── useScreenshotPolling.ts        # Screenshot refresh for non-streaming mode
│   ├── useDeviceGroups.ts             # Device group CRUD
│   └── usePageVisibility.ts           # Page visibility detection
└── api.ts                    # API client (typed fetch wrappers)
```

Frontend dev server runs on port 3000 and proxies `/api` and `/socket.io` to the backend.

### ADB layer

- [adb/](AutoGLM_GUI/adb/): Low-level ADB wrappers — `connection.py` (USB/WiFi/remote), `device.py` (device info), `input.py` (tap/swipe/keyboard), `screenshot.py`, `apps.py`, `timing.py`.
- [adb_plus/](AutoGLM_GUI/adb_plus/): Higher-level ADB utilities — `qr_pair.py` (QR code WiFi pairing via mDNS), `pair.py` (standard WiFi pairing), `mdns.py` (mDNS service discovery), `keyboard_installer.py` (ADB Keyboard APK installation), `touch.py` (normalized coordinate touch), `serial.py` (serial number extraction).

## Commands

### Setup

```bash
uv sync                          # Backend dependencies
cd frontend && pnpm install      # Frontend dependencies
cd electron && pnpm install      # Electron (desktop app only)
```

### Development

```bash
# Backend (hot reload via --reload)
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload

# Frontend dev server (port 3000, proxies to backend)
cd frontend && pnpm dev
```

### Lint & format

```bash
uv run python scripts/lint.py                  # Auto-fix all (backend + frontend)
uv run python scripts/lint.py --check-only     # Check only, no fixes
uv run python scripts/lint.py --backend --check-only   # Backend only, check
uv run python scripts/lint.py --frontend --check-only  # Frontend only, check

# Individual tools
uv run ruff check --fix                        # Backend lint
uv run ruff format                             # Backend format
uv run pyright AutoGLM_GUI/                    # Backend typecheck (Python 3.11 target)
cd frontend && pnpm lint                       # Frontend ESLint
cd frontend && pnpm format                     # Frontend Prettier
cd frontend && pnpm type-check                 # Frontend TypeScript
```

### Build

```bash
uv run python scripts/build.py                 # Build frontend + copy to backend static
uv run python scripts/build.py --pack          # Build + create wheel package
cd frontend && pnpm build                      # Frontend production build only
uv run python scripts/build_electron.py --publish never  # Electron app
```

### Tests

```bash
uv run pytest -v                                # Full test suite
uv run pytest -v tests/test_health_api.py       # Single test file
uv run pytest -v tests/integration/             # Integration tests only
uv run pytest -v tests/integration/test_docker_e2e.py -s  # Docker E2E
uv run pytest -v -m integration                 # Only integration-marked tests
```

Test markers (from [pytest.ini](pytest.ini)): `contract`, `integration`, `release_gate`.


## Debugging and observability

- Trace JSONL: `logs/trace_{date}.jsonl`. Each row has `trace_id`, `span_id`, `parent_span_id`, `name`, `duration_ms`, `attrs`.
- To debug a specific task: get its `trace_id` from `/api/tasks/{task_id}` or `/api/history/{serialno}/{record_id}`, then filter the JSONL: `grep '<trace_id>' logs/trace_*.jsonl | jq`.
- Prometheus metrics at `/api/metrics` aggregate latency distributions after task completion.
- Step timing breakdown is available in history as timing chips: screenshot, app detection, LLM, parsing, action execution, ADB, sleep.

## Key conventions

- Backend uses `uv` as the package manager; DO NOT use `pip install` for dependencies.
- Frontend uses `pnpm`; DO NOT use `npm` or `yarn`.
- Agent implementations follow the `AsyncAgent` protocol — add new agent types via the factory registry pattern, not by modifying `phone_agent_manager.py`.
- Device operations always go through `DeviceProtocol` — never call `adb shell` directly from agent code.
- Config changes flow through `config_manager` — read `get_effective_config()`, write through `update_config()`. Don't read env vars or CLI args directly.
- Lint scripts in `scripts/lint.py` orchestrate both backend (ruff, pyright) and frontend (ESLint, Prettier, tsc) — use them, not raw tool invocations, for CI parity.
- Commit style: Conventional Commits (`feat(scope):`, `fix(scope):`, `refactor(scope):`, etc.). Scopes: `api`, `frontend`, `device`, `agent`, `ui`, `build`, `docs`.
