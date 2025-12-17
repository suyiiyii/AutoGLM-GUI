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

1. **User Chat Request** → Frontend (`/chat` route) → WebSocket (`/ws/chat`) → Backend (`server.py`)
2. **Backend** → `PhoneAgent.run()` orchestrates the task
3. **PhoneAgent** → Uses `ModelClient` to call OpenAI-compatible LLM API with screenshots
4. **LLM Response** → `ActionHandler` executes phone actions via ADB
5. **Real-time Updates** → Streamed back through WebSocket to frontend

### Backend Architecture (`AutoGLM_GUI/`)

- **`server.py`**: FastAPI application with REST and WebSocket endpoints
  - `/api/init` - Initialize agent with model/agent configs
  - `/api/chat` - Chat endpoint (REST fallback)
  - `/ws/chat` - WebSocket chat with streaming responses
  - `/api/screenshot` - Capture device screenshot
  - `/api/tap` - Send tap command to device
  - `/api/scrcpy/stream` - H.264 video stream endpoint
  - `/api/scrcpy/info` - Get device resolution info
- **`scrcpy_stream.py`**: `ScrcpyStreamer` class manages scrcpy server lifecycle and H.264 video streaming
  - Spawns scrcpy-server process on device
  - Handles TCP socket for video data
  - Caches SPS/PPS/IDR frames for new client connections
  - Critical: Uses bundled `scrcpy-server-v3.3.3` binary (must be in project root and package)
- **`logger.py`**: Centralized logging configuration using loguru
  - Provides colorized console output with timestamps, levels, and source locations
  - Automatic file logging with rotation (100MB) and retention (7 days)
  - Separate error log files (50MB rotation, 30 days retention)
  - Configurable via CLI parameters (--log-level, --log-file, --no-log-file)
  - Used throughout AutoGLM_GUI/ (phone_agent/ uses original print statements)
- **`adb_plus/`**: Extended ADB utilities (screenshot capture, etc.)

### Phone Agent (`phone_agent/`)

Core automation engine from Open-AutoGLM:

- **`agent.py`**: `PhoneAgent` class - main orchestrator
  - `run(task)` - Execute a natural language task
  - `_execute_step()` - Single step: screenshot → LLM call → action execution
  - Manages conversation context and step counting
- **`actions/handler.py`**: `ActionHandler` - executes actions from LLM output
  - `do()` - Generic actions: tap, swipe, type, launch app, etc.
  - `finish()` - Task completion
  - `takeover()` - Human intervention request (login, CAPTCHA)
  - Coordinate normalization (0-1000 range → actual device pixels)
- **`adb/`**: Low-level ADB operations
  - `connection.py` - Device connection management
  - `device.py` - Device info (screen size, current app)
  - `input.py` - Touch/keyboard input
  - `screenshot.py` - Screenshot capture with Pillow
- **`model/client.py`**: `ModelClient` - OpenAI-compatible API client
  - Handles vision messages (text + base64 images)
  - Streaming support
- **`config/`**: Prompts and app definitions
  - `prompts.py` - System prompts (Chinese/English)
  - `apps.py` - Common Chinese app package names and aliases
  - `i18n.py` - Internationalization utilities

### Frontend Architecture (`frontend/src/`)

- **`routes/chat.tsx`**: Main chat interface
  - WebSocket connection to `/ws/chat`
  - Real-time video player (`ScrcpyPlayer` component)
  - Message history display
  - Manual tap controls on video stream
- **`components/ScrcpyPlayer.tsx`**: Scrcpy video player component
  - Uses `jmuxer` for H.264 decoding and playback
  - Fetches device resolution from `/api/scrcpy/info`
  - Handles coordinate transformation for tap events
  - Letterbox calculation for proper click positioning
  - Ripple animation on tap
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
- ✅ **Cross-platform**: Windows (x64) + macOS (ARM64)
- ✅ **No dependencies**: Bundles Python runtime, ADB, scrcpy-server
- ✅ **Auto-configuration**: Backend starts with bundled resources
- ✅ **Portable mode**: Windows supports portable .exe
- ✅ **UTF-8 handling**: PyInstaller runtime hook for Windows encoding

## Critical Implementation Details

### Video Streaming (Scrcpy)

- **Server Binary**: `scrcpy-server-v3.3.3` must exist at project root
- **Deployment**: Binary is bundled in wheel via `pyproject.toml` force-include
- **Stream Format**: Raw H.264 NAL units over TCP socket (port 27183)
- **Parameter Sets**: SPS/PPS are cached on first capture and sent to new clients for immediate playback
- **Coordinate Mapping**: Frontend gets device resolution (e.g., 1080x2400) and video size (e.g., 576x1280), calculates letterbox offsets, transforms click coords back to device scale

### Model API Integration

- **Compatible APIs**: Any OpenAI-compatible endpoint (智谱 BigModel, ModelScope, vLLM, SGLang)
- **Vision Messages**: Each step sends current screenshot as base64 PNG in message content
- **Response Format**: LLM returns JSON with `thinking` and `action` fields
- **Action Schema**: `{type: "do"|"finish"|"takeover", ...params}` parsed by `ActionHandler`

### ADB Device Control

- **Connection**: Uses `adb` CLI tool (must be in PATH)
- **Coordinate System**: LLM outputs normalized coords (0-1000), converted to pixels based on device resolution
- **Keyboard Handling**: Temporarily switches to ADB keyboard for text input, restores original after
- **Screenshot**: Captures via ADB screencap, converts to PNG with Pillow

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
  server.py            # FastAPI routes and WebSocket
  scrcpy_stream.py     # Scrcpy video streaming
  adb_plus/            # Extended ADB utilities
  static/              # Built frontend (copied from frontend/dist)

phone_agent/           # Core automation engine
  agent.py             # PhoneAgent orchestrator
  actions/handler.py   # Action execution
  adb/                 # Low-level ADB operations
  model/client.py      # LLM API client
  config/              # Prompts and app definitions

frontend/              # React frontend
  src/
    routes/chat.tsx    # Main UI
    components/ScrcpyPlayer.tsx
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

scripts/
  build.py             # Web app build
  build_electron.py    # Electron one-click build
  autoglm.spec         # PyInstaller configuration
  download_adb.py      # ADB downloader
  pyi_rth_utf8.py      # PyInstaller runtime hook (UTF-8)

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
- **phone_agent**: Third-party code, do NOT modify for compatibility
- **Encoding**: Use PyInstaller runtime hook for Windows UTF-8, not application code
- **Resources**: Always check `sys._MEIPASS` exists in PyInstaller environment


- phone_agent 下面是第三方的代码，目前通过直接拷贝代码的情况下进行引用，为了保持兼容性，任何时候不能修改里面的代码
- 运行 adb 命令的时候，尽量使用AutoGLM_GUI/platform_utils.py 下面的代码执行命令，为了更好的兼容性