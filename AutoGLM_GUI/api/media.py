"""Media routes: screenshot and stream reset."""

from __future__ import annotations

from fastapi import APIRouter

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.schemas import ScreenshotRequest, ScreenshotResponse
from AutoGLM_GUI.socketio_server import stop_streamers

router = APIRouter()


@router.post("/api/video/reset")
async def reset_video_stream(device_id: str | None = None) -> dict:
    """Reset active scrcpy streams (Socket.IO)."""
    stop_streamers(device_id=device_id)
    if device_id:
        logger.info("Video stream reset for device %s", device_id)
        return {
            "success": True,
            "message": f"Video stream reset for device {device_id}",
        }
    logger.info("All video streams reset")
    return {"success": True, "message": "All video streams reset"}


@router.post("/api/screenshot", response_model=ScreenshotResponse)
def take_screenshot(request: ScreenshotRequest) -> ScreenshotResponse:
    """获取设备截图。此操作无副作用，不影响 PhoneAgent 运行。"""
    try:
        from AutoGLM_GUI.platforms import ops as platform_ops

        resolved_device_type = platform_ops.resolve_device_type(
            device_id=request.device_id,
            device_type=request.device_type,
        )

        screenshot = platform_ops.take_screenshot(
            device_type=resolved_device_type,
            device_id=request.device_id,
            wda_url=request.wda_url,
        )
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
