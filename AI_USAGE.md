# AutoGLM-GUI - AI Agent Usage Guide

**If you are an AI Agent:** This is your complete guide to installing, configuring, and using AutoGLM-GUI via command line and API.
If you are a human user, please refer to [README.md](./README.md).

## Overview

AutoGLM-GUI is a phone agent platform that lets you control Android devices using natural language. You send a text instruction (e.g., "open WeChat and send a message"), and the vision model executes it by interacting with the device screen.

**Two ways to interact programmatically:**

| Method | Best For | Protocol |
|--------|----------|----------|
| **MCP** | Claude, Cursor, and other MCP-compatible AI agents | Model Context Protocol over HTTP |
| **REST API** | Any agent that can make HTTP calls | JSON over HTTP |

---

## Prerequisites

Before starting, confirm the following with the user:

- [ ] **Model API access**: The user must provide one of:
  - A third-party API endpoint (e.g., ZhiPu BigModel, ModelScope)
  - A self-hosted model server URL (e.g., vLLM, SGLang)
- [ ] **Android device**: Connected via USB or WiFi (ADB debugging enabled)
- [ ] **Python 3.11+** or **uv** installed on the system

> If the user has `uv` installed, you do NOT need Python pre-installed — `uv` will manage Python automatically.

---

## Step 1: Install AutoGLM-GUI

Install and start the server in one command. Choose based on what's available:

### Option A: Using uvx (Recommended)

No permanent installation needed. `uvx` runs in an isolated environment.

```bash
uvx autoglm-gui \
  --base-url {MODEL_API_URL} \
  --model {MODEL_NAME} \
  --apikey {API_KEY} \
  --no-browser \
  --port 8000
```

### Option B: Using pip

```bash
pip install autoglm-gui
autoglm-gui \
  --base-url {MODEL_API_URL} \
  --model {MODEL_NAME} \
  --apikey {API_KEY} \
  --no-browser \
  --port 8000
```

### Option C: Using Docker

```bash
docker run -d --name autoglm --network host \
  -e AUTOGLM_BASE_URL={MODEL_API_URL} \
  -e AUTOGLM_MODEL_NAME={MODEL_NAME} \
  -e AUTOGLM_API_KEY={API_KEY} \
  -v autoglm_config:/root/.config/autoglm \
  ghcr.io/suyiiyii/autoglm-gui:main
```

### Parameter Reference

Replace these placeholders with actual values from the user:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{MODEL_API_URL}` | Base URL of the vision model API | `https://open.bigmodel.cn/api/paas/v4` |
| `{MODEL_NAME}` | Model name | `autoglm-phone` |
| `{API_KEY}` | API key (omit `--apikey` if not required) | `sk-xxxxxxxx` |

### Common Model Configurations

**ZhiPu BigModel (recommended for beginners):**
```bash
uvx autoglm-gui \
  --base-url https://open.bigmodel.cn/api/paas/v4 \
  --model autoglm-phone \
  --apikey {API_KEY} \
  --no-browser --port 8000
```

**ModelScope:**
```bash
uvx autoglm-gui \
  --base-url https://api-inference.modelscope.cn/v1 \
  --model ZhipuAI/AutoGLM-Phone-9B \
  --apikey {API_KEY} \
  --no-browser --port 8000
```

**Self-hosted (vLLM/SGLang):**
```bash
uvx autoglm-gui \
  --base-url http://localhost:8080/v1 \
  --model autoglm-phone-9b \
  --no-browser --port 8000
```

**Expected output (all options):**
```
==================================================
  AutoGLM-GUI - Phone Agent Web Interface
==================================================
  Version:    1.5.12

  Server:     http://127.0.0.1:8000

  Model Configuration:
    Source:   CLI arguments
    Base URL: https://open.bigmodel.cn/api/paas/v4
    Model:    autoglm-phone
    API Key:  (configured)

==================================================
  Press Ctrl+C to stop
==================================================
```

**If you see `WARNING: base_url is not configured!`:** The `--base-url` parameter is missing or incorrect. Re-run the command with the correct URL.

> IMPORTANT: The server runs in the foreground. To run it in the background, append `&` (Unix) or use `nohup`. For Docker, the `-d` flag already handles this.

---

## Step 2: Verify Server is Running

```bash
curl -s http://127.0.0.1:8000/api/health
```

**Expected output:**
```json
{"status":"healthy","version":"1.5.12"}
```

**If it fails:** The server is not running or the port is different. Check the server output for the actual port number (auto-detected if 8000 is occupied).

---

## Step 3: Verify Android Device Connection

```bash
curl -s http://127.0.0.1:8000/api/devices | python3 -m json.tool
```

**Expected output (device connected):**
```json
{
  "devices": [
    {
      "id": "192.168.1.100:5555",
      "serial": "192.168.1.100:5555",
      "model": "Pixel 7",
      "status": "device",
      "connection_type": "wifi",
      "state": "online",
      "agent": null
    }
  ]
}
```

**If `"devices": []` (empty list):**
1. No Android device is connected. Ask the user to connect a device via USB or WiFi.
2. Ensure USB debugging is enabled on the device (Settings > Developer Options > USB Debugging).
3. ADB is automatically downloaded on first startup. If it fails, the user can install ADB manually.

Save the `id` field value — you will need it for all subsequent API calls. We refer to this as `{DEVICE_ID}` below.

---

## Using AutoGLM-GUI

Choose one of the two integration methods below.

---

## Method A: MCP Integration (for Claude, Cursor, etc.)

MCP (Model Context Protocol) is the cleanest integration path for AI agents that support it.

### MCP Endpoint

```
http://127.0.0.1:8000/mcp
```

### Available MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_devices()` | None | List all connected Android devices and their status |
| `chat(device_id, message)` | `device_id`: str, `message`: str | Send a natural language task to the phone agent (max 5 steps) |

### Claude Desktop Configuration

Add this to your Claude Desktop MCP config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "autoglm-gui": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Claude Code (CLI) Configuration

```bash
claude mcp add autoglm-gui --transport http http://127.0.0.1:8000/mcp
```

### MCP Usage Example

Once configured, you can use the tools directly in conversation:

1. Call `list_devices()` to get the device ID
2. Call `chat(device_id="{DEVICE_ID}", message="open Settings")` to execute a task

**Example response from `chat`:**
```json
{
  "result": "Successfully opened Settings app",
  "steps": 2,
  "success": true
}
```

### MCP Limitations

- Each `chat` call is limited to **5 steps** maximum
- If a task requires more steps, break it into smaller subtasks
- Each `chat` call resets the agent state (no conversation memory between calls)

---

## Method B: REST API (for Any Agent)

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/devices` | GET | List connected devices |
| `/api/chat` | POST | Execute a task (synchronous, waits for completion) |
| `/api/chat/stream` | POST | Execute a task with SSE streaming progress |
| `/api/chat/abort` | POST | Abort a running task |
| `/api/screenshot` | POST | Capture device screenshot (base64 PNG) |
| `/api/status` | GET | Get agent status |
| `/api/reset` | POST | Reset agent state |
| `/api/config` | GET | Get current configuration |
| `/api/config` | POST | Update configuration |

### Execute a Task (Synchronous)

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"device_id": "{DEVICE_ID}", "message": "open Settings"}'
```

**Expected output:**
```json
{
  "result": "Successfully opened Settings app",
  "steps": 2,
  "success": true
}
```

**If `"success": false`:** Check the `result` field for the error message. Common causes:
- Device is disconnected → verify with `GET /api/devices`
- Model API error → check the model configuration

### Execute a Task (Streaming)

For long-running tasks, use SSE streaming to get real-time progress:

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"device_id": "{DEVICE_ID}", "message": "open WeChat and send hello to File Transfer"}'
```

**SSE event types:**

| Event | Data Fields | Meaning |
|-------|-------------|---------|
| `step` | `thinking`, `action`, `step` | Agent executed one step |
| `done` | `message`, `success`, `steps` | Task completed |
| `error` | `message`, `hint` | Error occurred |
| `cancelled` | `message` | Task was aborted |

### Take a Screenshot

```bash
curl -X POST http://127.0.0.1:8000/api/screenshot \
  -H "Content-Type: application/json" \
  -d '{"device_id": "{DEVICE_ID}"}'
```

**Expected output:**
```json
{
  "success": true,
  "image": "iVBORw0KGgoAAAANSUhEUgAA...",
  "width": 1080,
  "height": 2400,
  "is_sensitive": false
}
```

The `image` field is a base64-encoded PNG. Decode it to view the screenshot.

### Abort a Running Task

```bash
curl -X POST http://127.0.0.1:8000/api/chat/abort \
  -H "Content-Type: application/json" \
  -d '{"device_id": "{DEVICE_ID}"}'
```

### Update Configuration at Runtime

```bash
curl -X POST http://127.0.0.1:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model_name": "autoglm-phone",
    "api_key": "sk-xxxxxxxx"
  }'
```

---

## Layered Agent API (Advanced)

The layered agent uses a **decision model** (e.g., GPT-4, Claude) for planning and the **vision model** for execution. This is useful for complex multi-step tasks.

### Prerequisites

The layered agent requires a separate decision model configuration. Set it via the config API:

```bash
curl -X POST http://127.0.0.1:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "decision_base_url": "{DECISION_MODEL_URL}",
    "decision_model_name": "{DECISION_MODEL_NAME}",
    "decision_api_key": "{DECISION_API_KEY}"
  }'
```

### Execute a Complex Task

```bash
curl -N -X POST http://127.0.0.1:8000/api/layered-agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "open WeChat, find the contact Alice, and send her: meeting at 3pm tomorrow",
    "device_id": "{DEVICE_ID}",
    "session_id": "session-001"
  }'
```

**SSE event types:**

| Event | Data Fields | Meaning |
|-------|-------------|---------|
| `tool_call` | `tool_name`, `tool_args` | Planner is calling a tool |
| `tool_result` | `tool_name`, `result` | Tool returned a result |
| `message` | `content` | Planner message |
| `done` | `content`, `success` | Task completed |
| `error` | `message` | Error occurred |

The `session_id` parameter maintains conversation context across multiple calls. Use the same `session_id` for follow-up tasks within the same session.

---

## Verification Checklist

After setup, verify everything works by running these checks in order:

```bash
# 1. Server is running
curl -s http://127.0.0.1:8000/api/health
# Expected: {"status":"healthy","version":"..."}

# 2. Device is connected
curl -s http://127.0.0.1:8000/api/devices
# Expected: "devices" array contains at least one device with "state":"online"

# 3. Agent can execute a task
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"device_id": "{DEVICE_ID}", "message": "what is on the screen right now?"}'
# Expected: {"result":"...","steps":1,"success":true}
```

**Success criteria:** All three checks pass. The third check returns `"success": true`.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `connection refused` on port 8000 | Server not running or port conflict | Start the server; check if port 8000 is in use with `lsof -i :8000` |
| `"devices": []` empty list | No Android device connected | Connect device via USB; enable USB debugging in Developer Options |
| `Device {id} is busy` (HTTP 409) | Another task is running on this device | Wait for the current task to finish, or call `/api/chat/abort` |
| `初始化失败` (HTTP 500) | Model API misconfigured | Verify `base_url`, `model_name`, and `api_key` via `GET /api/config` |
| `WARNING: base_url is not configured!` | Missing `--base-url` flag | Restart with `--base-url` or set via `POST /api/config` |
| `Max steps reached` with `success: false` | Task too complex for step limit | Break the task into smaller subtasks |
| `SCRCPY_SERVER_PATH` error | scrcpy-server binary not found | This is bundled in the pip package; reinstall with `pip install --force-reinstall autoglm-gui` |
| ADB download fails | Network issue during auto-download | Set `AUTOGLM_ADB_PATH` to a manually installed ADB path, or install ADB via system package manager |

---

## Environment Variables

All settings can be configured via environment variables instead of CLI flags:

| Variable | CLI Flag | Default |
|----------|----------|---------|
| `AUTOGLM_BASE_URL` | `--base-url` | (none) |
| `AUTOGLM_MODEL_NAME` | `--model` | `autoglm-phone-9b` |
| `AUTOGLM_API_KEY` | `--apikey` | (none) |
| `AUTOGLM_ADB_PATH` | — | auto-detect |
| `AUTOGLM_LOG_LEVEL` | `--log-level` | `INFO` |
| `AUTOGLM_CORS_ORIGINS` | — | `http://localhost:3000` |

---

## Command Quick Reference

```bash
# Install and start (one-liner)
uvx autoglm-gui --base-url {MODEL_API_URL} --model {MODEL_NAME} --apikey {API_KEY} --no-browser --port 8000

# Health check
curl -s http://127.0.0.1:8000/api/health

# List devices
curl -s http://127.0.0.1:8000/api/devices

# Execute task
curl -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"device_id":"{DEVICE_ID}","message":"open Settings"}'

# Screenshot
curl -X POST http://127.0.0.1:8000/api/screenshot -H "Content-Type: application/json" -d '{"device_id":"{DEVICE_ID}"}'

# Abort task
curl -X POST http://127.0.0.1:8000/api/chat/abort -H "Content-Type: application/json" -d '{"device_id":"{DEVICE_ID}"}'

# Get config
curl -s http://127.0.0.1:8000/api/config

# MCP endpoint (for Claude/Cursor)
# http://127.0.0.1:8000/mcp
```

---

## Notes

- **No authentication required:** The API server does not require Bearer tokens or API keys for its own endpoints. The `--apikey` flag is for the upstream model API, not for accessing AutoGLM-GUI itself.
- **Single device concurrency:** Each device can only run one task at a time. Attempting to send a second task to a busy device returns HTTP 409.
- **ADB auto-download:** If ADB is not found in PATH, AutoGLM-GUI will automatically download Android Platform Tools (~12MB) to `~/.cache/autoglm/platform-tools/`.
- **Coordinate system:** Touch coordinates (`/api/control/tap`, `/api/control/swipe`) use a 0-10000 normalized range, not pixel coordinates.

## ⚠️ Important

- **CRITICAL:** AutoGLM-GUI controls a real Android device. Tasks like "delete all messages" or "uninstall apps" will execute immediately with no undo. Always confirm destructive actions with the user before sending them to the agent.
- **CRITICAL:** The `--apikey` value is sensitive. Do not log it or include it in error reports.
- **IMPORTANT:** The `message` field in `/api/chat` has a 10,000 character limit.
