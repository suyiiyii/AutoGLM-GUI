"""Device control routes (tap/swipe/touch)."""

import asyncio

from fastapi import APIRouter

from AutoGLM_GUI.devices.adb_device import ADBDevice
from AutoGLM_GUI.devices import ScrcpyDevice
from AutoGLM_GUI import socketio_server as sio_server
from AutoGLM_GUI.schemas import (
    SwipeRequest,
    SwipeResponse,
    TapRequest,
    TapResponse,
    TouchDownRequest,
    TouchDownResponse,
    TouchMoveRequest,
    TouchMoveResponse,
    TouchUpRequest,
    TouchUpResponse,
)

router = APIRouter()


def _get_device_for_control(device_id: str) -> ADBDevice | ScrcpyDevice | None:
    """Get device for control, preferring scrcpy if available.

    Returns ScrcpyDevice if scrcpy control is available, otherwise ADBDevice.
    Returns None if scrcpy control is not available and ADB is not preferred.
    """
    # Try to use scrcpy control if available
    control_client = sio_server.get_scrcpy_control_client(device_id)
    if control_client:
        return ScrcpyDevice(device_id, control_client)
    # Fall back to ADB
    return ADBDevice(device_id)


@router.post("/api/control/tap", response_model=TapResponse)
async def control_tap(request: TapRequest) -> TapResponse:
    """Execute tap at specified device coordinates."""
    try:
        if not request.device_id:
            return TapResponse(success=False, error="device_id is required")

        device = _get_device_for_control(request.device_id)
        if device is None:
            return TapResponse(success=False, error="Device not available")

        await asyncio.to_thread(
            device.tap,
            x=request.x,
            y=request.y,
            delay=request.delay,
        )

        return TapResponse(success=True)
    except Exception as e:
        return TapResponse(success=False, error=str(e))


@router.post("/api/control/swipe", response_model=SwipeResponse)
async def control_swipe(request: SwipeRequest) -> SwipeResponse:
    """Execute swipe from start to end coordinates."""
    try:
        if not request.device_id:
            return SwipeResponse(success=False, error="device_id is required")

        device = _get_device_for_control(request.device_id)
        if device is None:
            return SwipeResponse(success=False, error="Device not available")

        await asyncio.to_thread(
            device.swipe,
            start_x=request.start_x,
            start_y=request.start_y,
            end_x=request.end_x,
            end_y=request.end_y,
            duration_ms=request.duration_ms,
            delay=request.delay,
        )

        return SwipeResponse(success=True)
    except Exception as e:
        return SwipeResponse(success=False, error=str(e))


@router.post("/api/control/touch/down", response_model=TouchDownResponse)
async def control_touch_down(request: TouchDownRequest) -> TouchDownResponse:
    """Send touch DOWN event at specified device coordinates."""
    try:
        if not request.device_id:
            return TouchDownResponse(success=False, error="device_id is required")

        device = _get_device_for_control(request.device_id)
        if device is None:
            return TouchDownResponse(success=False, error="Device not available")

        # Use scrcpy control if available, otherwise fallback to ADB
        if isinstance(device, ScrcpyDevice):
            await asyncio.to_thread(
                device.touch_down,
                x=request.x,
                y=request.y,
            )
        else:
            from AutoGLM_GUI.adb_plus import touch_down_async

            await touch_down_async(
                x=request.x,
                y=request.y,
                device_id=request.device_id,
                delay=request.delay,
            )

        return TouchDownResponse(success=True)
    except Exception as e:
        return TouchDownResponse(success=False, error=str(e))


@router.post("/api/control/touch/move", response_model=TouchMoveResponse)
async def control_touch_move(request: TouchMoveRequest) -> TouchMoveResponse:
    """Send touch MOVE event at specified device coordinates."""
    try:
        if not request.device_id:
            return TouchMoveResponse(success=False, error="device_id is required")

        device = _get_device_for_control(request.device_id)
        if device is None:
            return TouchMoveResponse(success=False, error="Device not available")

        # Use scrcpy control if available, otherwise fallback to ADB
        if isinstance(device, ScrcpyDevice):
            await asyncio.to_thread(
                device.touch_move,
                x=request.x,
                y=request.y,
            )
        else:
            from AutoGLM_GUI.adb_plus import touch_move_async

            await touch_move_async(
                x=request.x,
                y=request.y,
                device_id=request.device_id,
                delay=request.delay,
            )

        return TouchMoveResponse(success=True)
    except Exception as e:
        return TouchMoveResponse(success=False, error=str(e))


@router.post("/api/control/touch/up", response_model=TouchUpResponse)
async def control_touch_up(request: TouchUpRequest) -> TouchUpResponse:
    """Send touch UP event at specified device coordinates."""
    try:
        if not request.device_id:
            return TouchUpResponse(success=False, error="device_id is required")

        device = _get_device_for_control(request.device_id)
        if device is None:
            return TouchUpResponse(success=False, error="Device not available")

        # Use scrcpy control if available, otherwise fallback to ADB
        if isinstance(device, ScrcpyDevice):
            await asyncio.to_thread(
                device.touch_up,
                x=request.x,
                y=request.y,
            )
        else:
            from AutoGLM_GUI.adb_plus import touch_up_async

            await touch_up_async(
                x=request.x,
                y=request.y,
                device_id=request.device_id,
                delay=request.delay,
            )

        return TouchUpResponse(success=True)
    except Exception as e:
        return TouchUpResponse(success=False, error=str(e))
