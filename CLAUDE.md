# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoGLM-GUI is a modern web-based graphical interface for AutoGLM Phone Agent, enabling AI-powered Android device automation through a conversational interface with real-time screen monitoring.

**Key Technologies:**
- **Backend**: FastAPI (Python 3.10+) with WebSocket support
- **Frontend**: React 19 + TanStack Router + Tailwind CSS 4
- **Phone Integration**: ADB (Android Debug Bridge) + scrcpy for video streaming
- **Package Manager**: `uv` for Python, `pnpm` for frontend

## Development Commands

### Backend Development

All Python commands MUST use `uv run python` in the project root directory. Never execute `python` directly.

```bash
# Install dependencies
uv sync

# Run backend with auto-reload (development)
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload

# Run backend (production mode)
uv run autoglm-gui --base-url https://open.bigmodel.cn/api/paas/v4 \
  --model autoglm-phone \
  --apikey sk-xxxxx

# Run with custom log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
uv run autoglm-gui --base-url http://localhost:8080/v1 --log-level DEBUG

# Disable file logging (console only)
uv run autoglm-gui --base-url http://localhost:8080/v1 --no-log-file

# Custom log file path
uv run autoglm-gui --base-url http://localhost:8080/v1 --log-file logs/custom.log
```

### Frontend Development

```bash
# Install dependencies
cd frontend && pnpm install

# Development server (runs on port 3000)
cd frontend && pnpm dev

# Type checking
cd frontend && pnpm type-check

# Linting
cd frontend && pnpm lint
cd frontend && pnpm lint:fix

# Format code
cd frontend && pnpm format
cd frontend && pnpm format:check
```

### Building and Packaging

```bash
# Build frontend only (required before running backend)
uv run python scripts/build.py

# Build frontend + create Python package
uv run python scripts/build.py --pack

# Test built package locally
uvx --from dist/autoglm_gui-*.whl autoglm-gui

# Publish to PyPI
uv publish
```

### Electron Desktop Application

```bash
# One-click build (all platforms)
uv run python scripts/build_electron.py

# Build with skip options (faster incremental builds)
uv run python scripts/build_electron.py --skip-frontend  # Skip frontend rebuild
uv run python scripts/build_electron.py --skip-adb       # Skip ADB download
uv run python scripts/build_electron.py --skip-backend   # Skip backend repackaging

# Development mode (test Electron without building)
cd electron && npm run dev

# Build Electron only (requires resources prepared)
cd electron && npm run build
```

**Build Output**:
- **macOS**: `electron/dist/AutoGLM GUI-{version}-arm64.dmg`
- **Windows**: `electron/dist/AutoGLM GUI Setup {version}.exe` (installer)
- **Windows**: `electron/dist/AutoGLM GUI {version}.exe` (portable)
- **Linux**: `electron/dist/AutoGLM GUI-{version}.AppImage` (universal)
- **Linux**: `electron/dist/autoglm-gui_{version}_amd64.deb` (Debian/Ubuntu)
- **Linux**: `electron/dist/AutoGLM GUI-{version}.tar.gz` (portable)

## Configuration Management

### Configuration File

AutoGLM-GUI supports persistent configuration stored in `~/.config/autoglm/config.json`:

```json
{
  "base_url": "http://localhost:8080/v1",
  "model_name": "autoglm-phone-9b",
  "api_key": "sk-xxxxx"
}
```

### Configuration Priority

Configuration is loaded with the following priority (highest to lowest):

1. **CLI Arguments** (highest priority) - Override everything else
2. **Config File** (`~/.config/autoglm/config.json`) - Persistent settings
3. **Default Values** (lowest priority) - Built-in defaults

### Usage Examples

**First Time Setup (via Frontend)**:
1. Start: `uv run autoglm-gui`
2. Frontend opens config modal automatically (if no base_url configured)
3. Fill in `base_url`, `model_name`, `api_key`
4. Click "保存配置" (Save Configuration)
5. Configuration is saved to `~/.config/autoglm/config.json`

**Using Config File**:
```bash
# Start with saved configuration
uv run autoglm-gui

# The startup banner will show:
#   Configuration Source: config file (~/.config/autoglm/config.json)
```

**Using CLI Arguments (Override Config)**:
```bash
# CLI arguments override config file
uv run autoglm-gui --base-url http://localhost:8080/v1 --model autoglm-phone-9b

# The startup banner will show:
#   Configuration Source: CLI arguments
```

**Managing Config**:
- **View**: Click "全局配置" (Global Config) button in frontend sidebar
- **Edit**: Update via frontend modal and click "保存配置"
- **Delete**: Remove `~/.config/autoglm/config.json` manually
- **Check Current**: Backend startup banner shows config source

### Configuration API Endpoints

The frontend uses these API endpoints for configuration management:

- `GET /api/config` - Read current effective configuration
- `POST /api/config` - Save configuration to file
- `DELETE /api/config` - Delete configuration file

## ADB Keyboard Auto-Management

### Automatic Installation

AutoGLM-GUI automatically checks and installs ADB Keyboard when the Phone Agent is initialized:

1. **Per-Device Check**: Checks ADB Keyboard status only for the device being initialized
2. **Status Check**: Checks installation and enablement status on the device
3. **Auto Install**: If not installed, automatically installs the APK
4. **Auto Enable**: If not enabled, automatically enables the IME
5. **Logging**: All operations are logged to the log file

### APK Sources

Priority order:
1. **Bundled APK**: `AutoGLM_GUI/resources/apks/ADBKeyboard.apk` (included in wheel)
2. **Cached APK**: `~/.cache/autoglm/ADBKeyboard.apk`
3. **GitHub Download**: https://github.com/senzhk/ADBKeyBoard

### Auto-Setup Timing

ADB Keyboard is now checked and installed automatically when the frontend initializes the Phone Agent via `/api/init` endpoint, not during server startup. This provides:

- **Faster server startup**: No device scanning during startup
- **Per-device checking**: Only checks devices when they are actually used
- **Better user experience**: Installation progress is visible in the frontend

### Manual Installation

If automatic installation fails, you can install manually:

1. Download APK: https://github.com/senzhk/ADBKeyBoard/releases
2. Install: `adb install -r ADBKeyboard.apk`
3. Enable: Settings → Language & Input → Enable "ADB Keyboard"

### License Notice

ADB Keyboard uses the **GPL-2.0** license, which differs from AutoGLM-GUI's MIT license.
The APK file is bundled as an independent third-party component. When using it, you must comply with GPL-2.0 terms.

See: `AutoGLM_GUI/resources/apks/ADBKeyBoard.LICENSE.txt`

### Troubleshooting

**Issue**: Xiaomi devices cannot enable ADB Keyboard without root

**Solution**: See https://github.com/zai-org/Open-AutoGLM/issues/24

**Issue**: APK download fails (network unreachable)

**Solution**: The APK is bundled in the wheel, no download needed under normal circumstances

**Issue**: Device doesn't support ADB Keyboard

**Solution**: Check if the device allows third-party input methods, or try rooting the device

## Architecture

### Request Flow

**Basic Agent Flow**:
1. **User Chat Request** → Frontend (`ChatKitPanel.tsx`) → API (`/api/chat`) → Backend (`api/agents.py`)
2. **PhoneAgentManager** → `run_chat()` acquires device lock, gets or creates agent
3. **Agent.run()** → Orchestrates multi-step task execution
4. **Each Step**: Screenshot → LLM API (with vision) → `ActionHandler` → ADB execution
5. **Streaming Updates** → SSE (Server-Sent Events) → Frontend updates in real-time

**Layered Agent Flow** (NEW):
1. **User Request** → Frontend → API (`/api/layered/chat`) → Backend (`api/layered_agent.py`)
2. **Decision Model** → Plans high-level strategy using `openai-agents` session
3. **Function Tools** → Calls `do()` tool for device actions or `chat()` for information
4. **Vision Model** → PhoneAgent executes `do()` actions on device
5. **Session Persistence** → SQLiteSession stores conversation history
6. **Streaming** → SSE streams both decision thinking and execution updates

**Video Streaming Flow**:
1. **Frontend** → Socket.IO `connect-device` event → Backend (`socketio_server.py`)
2. **ScrcpyStreamer** → Starts scrcpy server on device, connects TCP socket (port 27183)
3. **H.264 Stream** → NAL units → Backend caches SPS/PPS/IDR frames
4. **Socket.IO** → Emits `video-data` events → Frontend (`ScrcpyPlayer.tsx`)
5. **jmuxer** → Decodes H.264 → Canvas rendering with letterbox

### Backend Architecture (`AutoGLM_GUI/`)

**Modular FastAPI Application**:
- **`server.py`**: Wrapper that imports the FastAPI app from `api/__init__.py`
- **`api/__init__.py`**: App factory pattern with modular routers:
  - `agents.py` - Agent lifecycle (init, chat, reset, abort, status)
  - `layered_agent.py` - Hierarchical execution with planning and execution layers
  - `devices.py` - Device discovery/management (list, WiFi, mDNS, QR pairing)
  - `control.py` - Direct device control (tap, swipe, screenshot)
  - `media.py` - Screenshot/video endpoints
  - `metrics.py` - Prometheus metrics
  - `version.py` - Version information
  - `workflows.py` - Workflow execution

**Core Backend Modules**:
- **`device_manager.py`**: Singleton managing device discovery and state
  - Two-layer device ID system (device_id for ADB, serial for aggregation)
  - Background polling thread (~2s intervals)
  - Connection priority: USB > WiFi > mDNS
  - mDNS discovery support
- **`phone_agent_manager.py`**: Singleton managing PhoneAgent lifecycle
  - Agent states: IDLE, BUSY, ERROR, INITIALIZING
  - Per-device locking (RLock) for concurrency control
  - Configuration hot-reload support
  - Streaming chat with abort capability
  - **NEW**: Agent storage (agents, configs) is now internal to the singleton
  - **Removed**: Dependency on global state.agents and state.agent_configs
- **`scrcpy_stream.py`**: `ScrcpyStreamer` class manages scrcpy server lifecycle and H.264 video streaming
  - Spawns scrcpy-server process on device
  - Handles TCP socket for video data
  - Caches SPS/PPS/IDR frames for new client connections
  - Critical: Uses bundled `scrcpy-server-v3.3.3` binary (must be in project root and package)
- **`socketio_server.py`**: Socket.IO integration for real-time video streaming
  - Events: `connect-device`, `disconnect`
  - Emits: `video-metadata`, `video-data`, `error`
- **`config_manager.py`**: Type-safe configuration management with Pydantic
  - Config file: `~/.config/autoglm/config.json`
  - Hot-reload support (mtime checking)
  - Validation for URLs and model names
- **`logger.py`**: Centralized logging configuration using loguru
  - Provides colorized console output with timestamps, levels, and source locations
  - Automatic file logging with rotation (100MB) and retention (7 days)
  - Separate error log files (50MB rotation, 30 days retention)
  - Configurable via CLI parameters (--log-level, --log-file, --no-log-file)
  - Used throughout AutoGLM_GUI/ (phone_agent/ uses original print statements)
- **`platform_utils.py`**: Cross-platform subprocess management
  - Async command execution (event loop safe)
  - Windows compatibility (subprocess.run vs asyncio)
- **`adb_plus/`**: Extended ADB utilities
  - `device.py` - Device availability and info
  - `screenshot.py` - Screenshot capture
  - `keyboard_installer.py` - ADB Keyboard auto-setup (GPL-2.0)
  - `qr_pair.py` - QR code pairing for wireless debugging
  - `serial.py` - Hardware serial extraction
  - `ip.py` - WiFi IP retrieval
  - `mdns.py` - mDNS device discovery
  - `touch.py` - Touch/swipe primitives

### Internal Agents (`AutoGLM_GUI/agents/`)

Internal implementations of automation agents:

- **`factory.py`**: Agent factory using registry pattern for creating different agent types.
- **`protocols.py`**: Base interfaces for all agents.
- **`glm/`**: GLM-based agent implementation.
- **`mai/`**: Internalized MAI Agent (Mobile Agent) with multi-image support.
- **`stream_runner.py`**: SSE streamer for agent execution steps.

### Action System (`AutoGLM_GUI/actions/`)

Executes actions parsed from LLM outputs:
- **`handler.py`**: Maps high-level actions (Tap, Swipe, Type) to ADB commands.
- **`types.py`**: Data models for action results.

### Device Identification (Two-Layer System)

AutoGLM-GUI uses a two-layer device identification system:

**Layer 1: `device_id` (ADB Execution Layer)**
- **Purpose**: Identifier passed to ADB commands (`adb -s {device_id}`)
- **Format depends on connection type**:
  - USB: Hardware serial number (e.g., `ABC123DEF456`)
  - WiFi: IP address and port (e.g., `192.168.1.100:5555`)
  - mDNS: Service name (e.g., `adb-243a09b7._adb-tls-connect._tcp`)
- **Usage**: API endpoints, PhoneAgent initialization, ADB command execution
- **Note**: `device_id` changes when connection method changes

**Layer 2: `serial` (Device Aggregation Layer)**
- **Purpose**: Stable, unique identifier for device aggregation in DeviceManager
- **Format**: Hardware serial number from `ro.serialno` property (e.g., `ABC123DEF456`)
- **Usage**: Internal device management, connection aggregation
- **Note**: `serial` never changes regardless of connection method

**Connection Switching Behavior**:
```
Example: Device initially connected via USB
  - device_id: "ABC123DEF456" (USB serial)
  - serial: "ABC123DEF456"

User switches to WiFi debugging
  - device_id: "192.168.1.100:5555" (WiFi IP:port) ← Changed!
  - serial: "ABC123DEF456" ← Unchanged

DeviceManager aggregates both connections:
  - Maintains device identity via serial
  - Automatically selects primary connection (USB > WiFi)
  - API continues using current device_id
```

**Important for API Integration**:
- When calling `/api/init`, `/api/chat`, etc., use the current `device_id`
- `device_id` may change during connection switches
- PhoneAgent instances are indexed by `device_id` in `state.agents`
- Connection switches may require agent reinitialization (future improvement: automatic migration)
- DeviceManager provides `get_agent_by_serial()` to find agents across connection changes

### Frontend Architecture (`frontend/src/`)

**Routing (TanStack Router)**:
```
/ (index.tsx)
├── /chat (chat.tsx) - Main chat interface
├── /workflows (workflows.tsx) - Workflow management
└── /about (about.tsx) - About page
```

**Root Layout** (`__root.tsx`):
- Theme provider (light/dark mode)
- i18n context (Chinese/English)
- Global error boundary
- Navigation sidebar

**Key Components**:
- **`ScrcpyPlayer.tsx`**: H.264 video player with Socket.IO streaming
  - Uses jmuxer for H.264 NAL unit decoding
  - WebCodecs Video Decoder API fallback
  - Canvas rendering with letterbox calculation
  - Touch coordinate transformation
  - Ripple animation on tap
- **`ChatKitPanel.tsx`**: Multi-mode chat interface
  - Basic mode: Direct PhoneAgent execution
  - Layered mode: Hierarchical task execution
- **`DevicePanel.tsx`**: Device info and initialization UI
  - Agent configuration (model, base URL, API key)
  - Connection status display
  - Initialization controls
- **`DeviceSidebar.tsx`**: Device list with connection management
  - USB/WiFi device listing
  - WiFi pairing controls
  - QR code pairing (wireless debugging)
  - mDNS device discovery
- **`api.ts`**: API client functions (uses `redaxios` - lightweight axios alternative)

### Electron Desktop Application (`electron/`)

AutoGLM-GUI can be packaged as a standalone desktop application using Electron, bundling the Python backend, ADB tools, and frontend into a single distributable package.

**Architecture**:
- **`main.js`**: Electron main process
  - Manages backend process lifecycle (spawn, health check, cleanup)
  - Dynamic port allocation (8000-8100 range)
  - Window creation and management
  - Environment setup (ADB PATH, PYTHONIOENCODING)
  - Error handling with user dialogs
  - Development and production mode support
- **`preload.js`**: Context isolation bridge between main and renderer
- **`afterPack.js`**: Post-build hook to set executable permissions (ADB, backend)

**Packaging Flow**:
1. **Frontend Build**: React app → `AutoGLM_GUI/static/`
2. **ADB Download**: Platform-specific tools → `resources/adb/{platform}/`
3. **Backend Packaging**: PyInstaller → `resources/backend/`
4. **Electron Build**: electron-builder → DMG/NSIS installers

**Key Features**:
- ✅ **Cross-platform**: Windows (x64) + macOS (ARM64) + Linux (x64)
- ✅ **No dependencies**: Bundles Python runtime, ADB, scrcpy-server
- ✅ **Auto-configuration**: Backend starts with bundled resources
- ✅ **Portable mode**: Windows supports portable .exe
- ✅ **UTF-8 handling**: PyInstaller runtime hook for Windows encoding

## Critical Implementation Details

### Video Streaming (Scrcpy)

- **Server Binary**: `scrcpy-server-v3.3.3` must exist at project root
- **Deployment**: Binary is bundled in wheel via `pyproject.toml` force-include
- **Stream Protocol**: Socket.IO-based H.264 NAL unit streaming
  - Backend: `socketio_server.py` emits `video-data` events
  - Frontend: `ScrcpyPlayer.tsx` receives and decodes via jmuxer
- **Stream Format**: Raw H.264 NAL units over TCP socket (port 27183)
- **Parameter Sets**: SPS/PPS/IDR frames are cached on first capture and sent to new clients for immediate playback
- **Coordinate Mapping**: Frontend gets device resolution (e.g., 1080x2400) and video size (e.g., 576x1280), calculates letterbox offsets, transforms click coords back to device scale

### Model API Integration

**Basic PhoneAgent Mode**:
- **Compatible APIs**: Any OpenAI-compatible endpoint (智谱 BigModel, ModelScope, vLLM, SGLang)
- **Vision Messages**: Each step sends current screenshot as base64 PNG in message content
- **Response Format**: LLM returns JSON with `thinking` and `action` fields
- **Action Schema**: `{type: "do"|"finish"|"takeover", ...params}` parsed by `ActionHandler`

**Layered Agent Mode** (NEW):
- **Architecture**: Hierarchical execution with planning and execution layers
- **Decision Layer**: Uses `openai-agents` library for session management and planning
- **Execution Layer**: PhoneAgent executes planned actions on device
- **Function Tools**: `do()` for device actions, `chat()` for information extraction
- **Session Persistence**: SQLiteSession stores conversation history
- **API Endpoint**: `/api/layered/chat` with streaming support

### ADB Device Control

- **Connection**: Uses `adb` CLI tool (must be in PATH)
- **Platform Utilities**: Always use `AutoGLM_GUI/platform_utils.py` for ADB command execution
  - Async command execution (event loop safe)
  - Cross-platform compatibility (Windows vs Unix)
- **Coordinate System**: LLM outputs normalized coords (0-1000), converted to pixels based on device resolution
- **Keyboard Handling**: Temporarily switches to ADB keyboard for text input, restores original after
- **Screenshot**: Captures via ADB screencap, converts to PNG with Pillow

### Concurrency Control and State Management

**PhoneAgentManager Locking**:
- **Manager Lock**: RLock for thread-safe manager operations
- **Per-Device Locks**: Dictionary of locks indexed by `device_id`
- **Prevents**: Concurrent execution on same device (would corrupt state)
- **Pattern**: Use `use_agent(device_id)` context manager for safe access

**DeviceManager Polling**:
- **Background Thread**: Runs every ~2 seconds in daemon thread
- **State Tracking**: Monitors device connections without blocking API
- **Connection Aggregation**: Groups connections by hardware serial
- **Primary Selection**: Automatically selects best connection (USB > WiFi)

**Streaming State**:
- **Per-Device Streamers**: Dictionary in `state.scrcpy_streamers`
- **Stream Locks**: Async locks in `state.scrcpy_locks` prevent concurrent starts
- **Cleanup**: Automatic cleanup on disconnect or error

**Agent State Management** (NEW):
- **Storage**: Agent instances and configs are stored internally in PhoneAgentManager singleton
- **Thread Safety**: All state access is protected by `self._manager_lock` (RLock)
- **No Global State**: Removed dependency on `state.agents` and `state.agent_configs` in 2026 refactoring
- **Benefits**:
  - **Encapsulation**: Manager owns its state completely
  - **Testability**: Easier to test in isolation
  - **Clarity**: Single source of truth for agent lifecycle
  - **Safety**: No risk of external code accidentally modifying global state
- **API**: Always use PhoneAgentManager methods (get_agent, use_agent, etc.) for state access

### Logging System

- **Library**: loguru - modern Python logging with zero configuration
- **Scope**: Only AutoGLM_GUI/ directory (phone_agent/ keeps original print statements for compatibility)
- **Console Output**:
  - Colorized output with timestamps, log levels, and source locations
  - Default level: INFO (adjustable via --log-level)
  - Format: `YYYY-MM-DD HH:mm:ss.SSS | LEVEL | module:function:line - message`
- **File Output**:
  - Main log: `logs/autoglm_{time:YYYY-MM-DD}.log` (all levels ≥ DEBUG)
  - Error log: `logs/errors_{time:YYYY-MM-DD}.log` (only ERROR and above)
  - Rotation: 100MB for main log, 50MB for error log
  - Retention: 7 days for main log, 30 days for error log
  - Compression: zip format for rotated logs
- **Usage in Code**:
  ```python
  from AutoGLM_GUI.logger import logger

  logger.debug("Detailed information for debugging")
  logger.info("Normal operation messages")
  logger.warning("Warning messages")
  logger.error("Error messages")
  logger.exception("Exception with full stack trace")
  ```
- **Log Levels**:
  - DEBUG: NAL unit caching, initialization data details, sent NAL counts
  - INFO: Server startup, device connections, stream lifecycle events
  - WARNING: Retries, failed operations with recovery, takeover requests
  - ERROR: Failed starts, connection errors, unexpected exceptions

## Configuration

### Environment Variables

```bash
# Optional defaults (overridden by CLI args)
AUTOGLM_BASE_URL=http://localhost:8080/v1
AUTOGLM_MODEL_NAME=autoglm-phone-9b
AUTOGLM_API_KEY=EMPTY

# Optional scrcpy server path
SCRCPY_SERVER_PATH=/path/to/scrcpy-server
```

### CLI Arguments

See `AutoGLM_GUI/__main__.py` for full list. Key args:
- `--base-url` (required): Model API endpoint
- `--model`: Model name (default: autoglm-phone-9b)
- `--apikey`: API key
- `--host`: Server host (default: 127.0.0.1)
- `--port`: Server port (default: 8000, auto-finds if occupied)
- `--log-level`: Console log level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
- `--log-file`: Log file path (default: logs/autoglm_{time:YYYY-MM-DD}.log)
- `--no-log-file`: Disable file logging (console only)
- `--no-browser`: Skip auto-opening browser
- `--reload`: Enable uvicorn auto-reload (development only)

## Package Structure

```
AutoGLM_GUI/           # Backend FastAPI app (entry point)
  __main__.py          # CLI entry point
  server.py            # FastAPI + Socket.IO wrapper
  api/                 # Modular route handlers
    __init__.py        # App factory
    agents.py          # Agent lifecycle
    layered_agent.py   # Layered agent API
    devices.py         # Device management
    control.py         # Direct device control
    media.py           # Screenshot/video
    metrics.py         # Prometheus metrics
    version.py         # Version info
    workflows.py       # Workflow execution
  scrcpy_stream.py     # Scrcpy video streaming
  socketio_server.py   # Socket.IO integration
  device_manager.py    # Device discovery singleton
  phone_agent_manager.py # Agent lifecycle singleton
  config_manager.py    # Type-safe config management
  logger.py            # Loguru logging setup
  platform_utils.py    # Cross-platform utilities
  adb_plus/            # Extended ADB utilities
    device.py
    screenshot.py
    keyboard_installer.py
    qr_pair.py
    serial.py
    ip.py
    mdns.py
    touch.py
  agents/              # Internal agent implementations
    glm/
    mai/
    factory.py
  static/              # Built frontend (copied from frontend/dist)
  resources/           # Bundled resources
    apks/              # ADB Keyboard APK (GPL-2.0)

frontend/              # React frontend
  src/
    routes/
      chat.tsx         # Main chat interface
      workflows.tsx    # Workflow management
      __root.tsx       # Layout + theme
    components/
      ScrcpyPlayer.tsx # Video player
      ChatKitPanel.tsx # Multi-mode chat
      DevicePanel.tsx  # Device UI
      DeviceSidebar.tsx # Device list
    api.ts             # API client
  dist/                # Build output (not in git)

electron/              # Electron desktop application
  main.js              # Main process (backend lifecycle)
  preload.js           # Context bridge
  afterPack.js         # Post-build hook (permissions)
  electron-builder.yml # Packaging configuration
  package.json         # Electron dependencies
  dist/                # Built installers (not in git)

resources/             # Bundled resources (not in git)
  backend/             # PyInstaller output
  adb/                 # Platform-specific ADB tools
    windows/
    darwin/
    linux/

scripts/
  build.py             # Web app build
  build_electron.py    # Electron one-click build
  autoglm.spec         # PyInstaller configuration
  download_adb.py      # ADB downloader
  pyi_rth_utf8.py      # PyInstaller runtime hook (UTF-8)
  lint.py              # Code linting

scrcpy-server-v3.3.3   # Scrcpy server binary (bundled)
```

## Common Pitfalls

### Web Application
1. **Missing scrcpy-server**: Video streaming fails if binary is missing or not bundled correctly in wheel
2. **Coordinate Mismatch**: Frontend must fetch actual device resolution via `/api/scrcpy/info` before sending taps
3. **Python Execution**: Always use `uv run python`, never plain `python`
4. **Frontend Not Built**: Backend serves static files from `AutoGLM_GUI/static/` - must run `scripts/build.py` first
5. **ADB Not in PATH**: All ADB operations will fail silently or with cryptic errors
6. **Model API Compatibility**: LLM must support vision inputs (base64 images) and follow action schema conventions
7. **Direct State Access**: Never access `state.agents` directly - use `PhoneAgentManager.use_agent()` context manager
8. **ADB Command Execution**: Always use `platform_utils.py` functions instead of direct subprocess calls
9. **Device ID vs Serial**: Remember `device_id` changes with connection type, `serial` is stable
10. **Concurrent Execution**: PhoneAgentManager prevents concurrent tasks on same device - respect the locks
11. **Legacy Code**: `phone_agent` and `mai_agent` directories are third-party legacy code kept for reference only - use internal agents in `AutoGLM_GUI/agents/`

### Electron Desktop Application
1. **Resources Not Prepared**: Electron build requires `resources/backend/` and `resources/adb/` - use `build_electron.py`
2. **Executable Permissions**: On macOS/Linux, ADB and backend must have execute permissions - handled by `afterPack.js`
3. **Windows Encoding**: Python backend uses PyInstaller runtime hook (`pyi_rth_utf8.py`) for UTF-8, don't modify `__main__.py` encoding
4. **macOS Unsigned App**: First launch may be blocked by Gatekeeper - use `xattr -cr "AutoGLM GUI.app"` or right-click → Open
5. **Port Conflicts**: Electron auto-finds available port (8000-8100), but may fail if all ports occupied
6. **Backend Startup Timeout**: If backend doesn't respond within 30s, check logs and ensure all dependencies bundled correctly
7. **Path Issues in PyInstaller**: Always use `sys._MEIPASS` for bundled resource paths, see `scrcpy_stream.py` and `api/__init__.py`

## Development Workflow

### Web Application Development
1. Make frontend changes → `cd frontend && pnpm dev` (hot reload)
2. Make backend changes → `uv run autoglm-gui --reload` (auto-reload enabled)
3. Before committing code, run linting: `uv run python scripts/lint.py`
4. Before package release:
   - Build frontend: `uv run python scripts/build.py`
   - Test locally: `uv run autoglm-gui`
   - Build package: `uv run python scripts/build.py --pack`
   - Test wheel: `uvx --from dist/autoglm_gui-*.whl autoglm-gui`
   - Publish: `uv publish`

### Electron Desktop Application Development
1. **Initial Setup**:
   ```bash
   cd electron && npm install
   ```

2. **Development Mode** (without packaging):
   ```bash
   # Terminal 1: Run backend directly
   uv run autoglm-gui --base-url http://localhost:8080/v1

   # Terminal 2: Run Electron in dev mode
   cd electron && npm run dev
   ```

3. **Test Full Build** (with packaging):
   ```bash
   # One-click build everything
   uv run python scripts/build_electron.py

   # Or incremental build (skip unchanged parts)
   uv run python scripts/build_electron.py --skip-frontend --skip-adb
   ```

4. **Test Built Application**:
   - **macOS**: `open "electron/dist/mac-arm64/AutoGLM GUI.app"`
   - **Windows**: Run `electron\dist\AutoGLM GUI Setup {version}.exe`

5. **CI/CD**: Push to `main` or `dev` branch triggers GitHub Actions
   - Builds Windows + macOS installers automatically
   - Downloads artifacts from Actions tab

### Important Notes
- **Legacy Directories**: `phone_agent` and `mai_agent` are third-party code, do NOT modify
- **Encoding**: Use PyInstaller runtime hook for Windows UTF-8, not application code
- **Resources**: Always check `sys._MEIPASS` exists in PyInstaller environment
- **ADB**: Use `AutoGLM_GUI/platform_utils.py` for executing commands
- **Refactoring**: Prefer internal agent implementations in `AutoGLM_GUI/agents/`
