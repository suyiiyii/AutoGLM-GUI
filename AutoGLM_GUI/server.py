"""AutoGLM-GUI Backend API Server."""

import asyncio
import json
import os
from importlib.metadata import version as get_version
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig
from pydantic import BaseModel, Field

from AutoGLM_GUI.adb_plus import capture_screenshot
from AutoGLM_GUI.scrcpy_stream import ScrcpyStreamer

# 全局 scrcpy streamer 实例和锁
scrcpy_streamer: ScrcpyStreamer | None = None
scrcpy_lock = asyncio.Lock()

# 获取包版本号
try:
    __version__ = get_version("autoglm-gui")
except Exception:
    __version__ = "dev"

app = FastAPI(title="AutoGLM-GUI API", version=__version__)

# CORS 配置 (开发环境需要)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局单例 agent
agent: PhoneAgent | None = None
last_model_config: ModelConfig | None = None
last_agent_config: AgentConfig | None = None

# 默认配置 (优先从环境变量读取，支持 reload 模式)
DEFAULT_BASE_URL: str = os.getenv("AUTOGLM_BASE_URL", "")
DEFAULT_MODEL_NAME: str = os.getenv("AUTOGLM_MODEL_NAME", "autoglm-phone-9b")
DEFAULT_API_KEY: str = os.getenv("AUTOGLM_API_KEY", "EMPTY")


def _non_blocking_takeover(message: str) -> None:
    """Log takeover requests without blocking for console input."""
    print(f"[Takeover] {message}")


# 请求/响应模型
class APIModelConfig(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2


class APIAgentConfig(BaseModel):
    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True


class InitRequest(BaseModel):
    model: APIModelConfig | None = Field(default=None, alias="model_config")
    agent: APIAgentConfig | None = Field(default=None, alias="agent_config")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    result: str
    steps: int
    success: bool


class StatusResponse(BaseModel):
    version: str
    initialized: bool
    step_count: int


class ScreenshotRequest(BaseModel):
    device_id: str | None = None


class ScreenshotResponse(BaseModel):
    success: bool
    image: str  # base64 encoded PNG
    width: int
    height: int
    is_sensitive: bool
    error: str | None = None


class TapRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TapResponse(BaseModel):
    success: bool
    error: str | None = None


class SwipeRequest(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration_ms: int | None = None
    device_id: str | None = None
    delay: float = 0.0


class SwipeResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchDownRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TouchDownResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchMoveRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TouchMoveResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchUpRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TouchUpResponse(BaseModel):
    success: bool
    error: str | None = None


# API 端点
@app.post("/api/init")
def init_agent(request: InitRequest) -> dict:
    """初始化 PhoneAgent。"""
    global agent, last_model_config, last_agent_config

    # 提取配置或使用空对象
    req_model_config = request.model or APIModelConfig()
    req_agent_config = request.agent or APIAgentConfig()

    # 使用请求参数或默认值
    base_url = req_model_config.base_url or DEFAULT_BASE_URL
    api_key = req_model_config.api_key or DEFAULT_API_KEY
    model_name = req_model_config.model_name or DEFAULT_MODEL_NAME

    if not base_url:
        raise HTTPException(
            status_code=400, detail="base_url is required (in model_config or env)"
        )

    model_config = ModelConfig(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        max_tokens=req_model_config.max_tokens,
        temperature=req_model_config.temperature,
        top_p=req_model_config.top_p,
        frequency_penalty=req_model_config.frequency_penalty,
    )

    agent_config = AgentConfig(
        max_steps=req_agent_config.max_steps,
        device_id=req_agent_config.device_id,
        lang=req_agent_config.lang,
        system_prompt=req_agent_config.system_prompt,
        verbose=req_agent_config.verbose,
    )

    agent = PhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
        takeover_callback=_non_blocking_takeover,
    )

    # 记录最新配置，便于 reset 时自动重建
    last_model_config = model_config
    last_agent_config = agent_config

    return {"success": True, "message": "Agent initialized"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """发送任务给 Agent 并执行。"""
    global agent

    if agent is None:
        raise HTTPException(
            status_code=400, detail="Agent not initialized. Call /api/init first."
        )

    try:
        result = agent.run(request.message)
        steps = agent.step_count
        agent.reset()

        return ChatResponse(result=result, steps=steps, success=True)
    except Exception as e:
        return ChatResponse(result=str(e), steps=0, success=False)


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """发送任务给 Agent 并实时推送执行进度（SSE）。"""
    global agent

    if agent is None:
        raise HTTPException(
            status_code=400, detail="Agent not initialized. Call /api/init first."
        )

    def event_generator():
        """SSE 事件生成器"""
        try:
            # 使用 step() 逐步执行
            step_result = agent.step(request.message)
            while True:
                # 发送 step 事件
                event_data = {
                    "type": "step",
                    "step": agent.step_count,
                    "thinking": step_result.thinking,
                    "action": step_result.action,
                    "success": step_result.success,
                    "finished": step_result.finished,
                }

                yield "event: step\n"
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                if step_result.finished:
                    done_data = {
                        "type": "done",
                        "message": step_result.message,
                        "steps": agent.step_count,
                        "success": step_result.success,
                    }
                    yield "event: done\n"
                    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                    break

                if agent.step_count >= agent.agent_config.max_steps:
                    done_data = {
                        "type": "done",
                        "message": "Max steps reached",
                        "steps": agent.step_count,
                        "success": step_result.success,
                    }
                    yield "event: done\n"
                    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                    break

                step_result = agent.step()

            # 任务完成后重置
            agent.reset()

        except Exception as e:
            # 发送错误事件
            error_data = {
                "type": "error",
                "message": str(e),
            }
            yield "event: error\n"
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@app.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    """获取 Agent 状态和版本信息。"""
    global agent

    return StatusResponse(
        version=__version__,
        initialized=agent is not None,
        step_count=agent.step_count if agent else 0,
    )


@app.post("/api/reset")
def reset_agent() -> dict:
    """重置 Agent 状态。"""
    global agent, last_model_config, last_agent_config

    reinitialized = False

    # 先清空当前实例
    if agent is not None:
        agent.reset()

    # 如有历史配置，自动重建实例；否则置空
    if last_model_config and last_agent_config:
        agent = PhoneAgent(
            model_config=last_model_config,
            agent_config=last_agent_config,
            takeover_callback=_non_blocking_takeover,
        )
        reinitialized = True
    else:
        agent = None

    return {
        "success": True,
        "message": "Agent reset",
        "reinitialized": reinitialized,
    }


@app.post("/api/video/reset")
async def reset_video_stream() -> dict:
    """Reset video stream (cleanup scrcpy server)."""
    global scrcpy_streamer

    async with scrcpy_lock:
        if scrcpy_streamer is not None:
            print("[video/reset] Stopping existing streamer...")
            scrcpy_streamer.stop()
            scrcpy_streamer = None
            print("[video/reset] Streamer reset complete")
            return {"success": True, "message": "Video stream reset"}
        else:
            return {"success": True, "message": "No active video stream"}


@app.post("/api/screenshot", response_model=ScreenshotResponse)
def take_screenshot(request: ScreenshotRequest) -> ScreenshotResponse:
    """获取设备截图。此操作无副作用，不影响 PhoneAgent 运行。"""
    try:
        screenshot = capture_screenshot(device_id=request.device_id)
        return ScreenshotResponse(
            success=True,
            image=screenshot.base64_data,
            width=screenshot.width,
            height=screenshot.height,
            is_sensitive=screenshot.is_sensitive,
        )
    except Exception as e:
        return ScreenshotResponse(
            success=False,
            image="",
            width=0,
            height=0,
            is_sensitive=False,
            error=str(e),
        )


@app.post("/api/control/tap", response_model=TapResponse)
def control_tap(request: TapRequest) -> TapResponse:
    """Execute tap at specified device coordinates."""
    try:
        from phone_agent.adb import tap

        tap(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay
        )

        return TapResponse(success=True)
    except Exception as e:
        return TapResponse(success=False, error=str(e))


@app.post("/api/control/swipe", response_model=SwipeResponse)
def control_swipe(request: SwipeRequest) -> SwipeResponse:
    """Execute swipe from start to end coordinates."""
    try:
        from phone_agent.adb import swipe

        swipe(
            start_x=request.start_x,
            start_y=request.start_y,
            end_x=request.end_x,
            end_y=request.end_y,
            duration_ms=request.duration_ms,
            device_id=request.device_id,
            delay=request.delay
        )

        return SwipeResponse(success=True)
    except Exception as e:
        return SwipeResponse(success=False, error=str(e))


@app.post("/api/control/touch/down", response_model=TouchDownResponse)
def control_touch_down(request: TouchDownRequest) -> TouchDownResponse:
    """Send touch DOWN event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_down

        touch_down(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay
        )

        return TouchDownResponse(success=True)
    except Exception as e:
        return TouchDownResponse(success=False, error=str(e))


@app.post("/api/control/touch/move", response_model=TouchMoveResponse)
def control_touch_move(request: TouchMoveRequest) -> TouchMoveResponse:
    """Send touch MOVE event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_move

        touch_move(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay
        )

        return TouchMoveResponse(success=True)
    except Exception as e:
        return TouchMoveResponse(success=False, error=str(e))


@app.post("/api/control/touch/up", response_model=TouchUpResponse)
def control_touch_up(request: TouchUpRequest) -> TouchUpResponse:
    """Send touch UP event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_up

        touch_up(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay
        )

        return TouchUpResponse(success=True)
    except Exception as e:
        return TouchUpResponse(success=False, error=str(e))


@app.websocket("/api/video/stream")
async def video_stream_ws(websocket: WebSocket):
    """Stream real-time H.264 video from scrcpy server via WebSocket."""
    global scrcpy_streamer

    await websocket.accept()
    print("[video/stream] WebSocket connection accepted")

    # Use global lock to prevent concurrent streamer initialization
    async with scrcpy_lock:
        # Reuse existing streamer if available
        if scrcpy_streamer is None:
            print("[video/stream] Creating new streamer instance...")
            scrcpy_streamer = ScrcpyStreamer(max_size=1280, bit_rate=4_000_000)

            try:
                print("[video/stream] Starting scrcpy server...")
                await scrcpy_streamer.start()
                print("[video/stream] Scrcpy server started successfully")
            except Exception as e:
                import traceback
                print(f"[video/stream] Failed to start streamer: {e}")
                print(f"[video/stream] Traceback:\n{traceback.format_exc()}")
                scrcpy_streamer.stop()
                scrcpy_streamer = None
                try:
                    await websocket.send_json({"error": str(e)})
                except Exception:
                    pass
                return
        else:
            print("[video/stream] Reusing existing streamer instance")

            # Send ONLY SPS/PPS (not IDR) to initialize decoder
            # Client will then wait for next live IDR frame (max 1s with i-frame-interval=1)
            # This avoids issues with potentially corrupted cached IDR frames
            if scrcpy_streamer.cached_sps and scrcpy_streamer.cached_pps:
                init_data = scrcpy_streamer.cached_sps + scrcpy_streamer.cached_pps
                await websocket.send_bytes(init_data)
                print(f"[video/stream] ✓ Sent SPS/PPS ({len(init_data)} bytes), client will wait for live IDR")
            else:
                print("[video/stream] ⚠ Warning: No cached SPS/PPS available")

    # Stream H.264 data to client
    stream_failed = False
    try:
        chunk_count = 0
        while True:
            try:
                h264_chunk = await scrcpy_streamer.read_h264_chunk()
                await websocket.send_bytes(h264_chunk)
                chunk_count += 1
                if chunk_count % 100 == 0:
                    print(f"[video/stream] Sent {chunk_count} chunks")
            except ConnectionError as e:
                print(f"[video/stream] Connection error after {chunk_count} chunks: {e}")
                stream_failed = True
                # Don't send error if WebSocket already disconnected
                try:
                    await websocket.send_json({"error": f"Stream error: {str(e)}"})
                except Exception:
                    pass
                break

    except WebSocketDisconnect:
        print("[video/stream] Client disconnected")
    except Exception as e:
        import traceback
        print(f"[video/stream] Error: {e}")
        print(f"[video/stream] Traceback:\n{traceback.format_exc()}")
        stream_failed = True
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass

    # Reset global streamer if stream failed
    if stream_failed:
        async with scrcpy_lock:
            print("[video/stream] Stream failed, resetting global streamer...")
            if scrcpy_streamer is not None:
                scrcpy_streamer.stop()
                scrcpy_streamer = None

    print("[video/stream] Client stream ended")


# 静态文件托管 - 使用包内资源定位
def _get_static_dir() -> Path | None:
    """获取静态文件目录路径。"""
    try:
        # 尝试从包内资源获取
        static_dir = files("AutoGLM_GUI").joinpath("static")
        if hasattr(static_dir, "_path"):
            # Traversable 对象
            path = Path(str(static_dir))
            if path.exists():
                return path
        # 直接转换为 Path
        path = Path(str(static_dir))
        if path.exists():
            return path
    except (TypeError, FileNotFoundError):
        pass

    return None


STATIC_DIR = _get_static_dir()

if STATIC_DIR is not None and STATIC_DIR.exists():
    # 托管静态资源
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # 所有非 API 路由返回 index.html (支持前端路由)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve the SPA for all non-API routes."""
        # 如果请求的是具体文件且存在，则返回该文件
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # 否则返回 index.html (支持前端路由)
        return FileResponse(STATIC_DIR / "index.html")
