"""Media routes: screenshot and stream reset."""

from __future__ import annotations

from fastapi import APIRouter

from AutoGLM_GUI.adb_plus import capture_screenshot
from AutoGLM_GUI.exceptions import DeviceNotAvailableError
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
    from AutoGLM_GUI.device_manager import DeviceManager

    try:
        device_id = request.device_id

        if not device_id:
            return ScreenshotResponse(
                success=False,
                image="",
                width=0,
                height=0,
                is_sensitive=False,
                error="device_id is required",
            )

        device_manager = DeviceManager.get_instance()
        serial = device_manager.get_serial_by_device_id(device_id)

        if not serial:
            return ScreenshotResponse(
                success=False,
                image="",
                width=0,
                height=0,
                is_sensitive=False,
                error=f"Device {device_id} not found",
            )

        if serial:
            managed = device_manager._devices.get(serial)
            if managed and managed.connection_type.value == "remote":
                remote_device = device_manager.get_remote_device_instance(serial)

                if not remote_device:
                    return ScreenshotResponse(
                        success=False,
                        image="",
                        width=0,
                        height=0,
                        is_sensitive=False,
                        error=f"Remote device {serial} not found",
                    )

                screenshot = remote_device.get_screenshot(timeout=10)  # type: ignore
                return ScreenshotResponse(
                    success=True,
                    image=screenshot.base64_data,
                    width=screenshot.width,
                    height=screenshot.height,
                    is_sensitive=screenshot.is_sensitive,
                )

        screenshot = capture_screenshot(device_id=device_id)
        return ScreenshotResponse(
            success=True,
            image=screenshot.base64_data,
            width=screenshot.width,
            height=screenshot.height,
            is_sensitive=screenshot.is_sensitive,
        )
    except DeviceNotAvailableError as e:
        logger.warning("Screenshot failed - device not available: %s", e)
        return ScreenshotResponse(
            success=False,
            image="",
            width=0,
            height=0,
            is_sensitive=False,
            error=str(e),
        )
    except Exception as e:
        logger.exception("Screenshot failed for device %s", request.device_id)
        return ScreenshotResponse(
            success=False,
            image="",
            width=0,
            height=0,
            is_sensitive=False,
            error=str(e),
        )
