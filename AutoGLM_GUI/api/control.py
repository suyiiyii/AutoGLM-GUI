"""Device control routes (tap/swipe/touch)."""

from fastapi import APIRouter

from AutoGLM_GUI.devices.adb_device import ADBDevice
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


@router.post("/api/control/tap", response_model=TapResponse)
def control_tap(request: TapRequest) -> TapResponse:
    """Execute tap at specified device coordinates."""
    try:
        if not request.device_id:
            return TapResponse(success=False, error="device_id is required")

        device = ADBDevice(request.device_id)
        device.tap(
            x=request.x,
            y=request.y,
            delay=request.delay,
        )

        return TapResponse(success=True)
    except Exception as e:
        return TapResponse(success=False, error=str(e))


@router.post("/api/control/swipe", response_model=SwipeResponse)
def control_swipe(request: SwipeRequest) -> SwipeResponse:
    """Execute swipe from start to end coordinates."""
    try:
        if not request.device_id:
            return SwipeResponse(success=False, error="device_id is required")

        device = ADBDevice(request.device_id)
        device.swipe(
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
def control_touch_down(request: TouchDownRequest) -> TouchDownResponse:
    """Send touch DOWN event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_down

        touch_down(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay,
        )

        return TouchDownResponse(success=True)
    except Exception as e:
        return TouchDownResponse(success=False, error=str(e))


@router.post("/api/control/touch/move", response_model=TouchMoveResponse)
def control_touch_move(request: TouchMoveRequest) -> TouchMoveResponse:
    """Send touch MOVE event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_move

        touch_move(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay,
        )

        return TouchMoveResponse(success=True)
    except Exception as e:
        return TouchMoveResponse(success=False, error=str(e))


@router.post("/api/control/touch/up", response_model=TouchUpResponse)
def control_touch_up(request: TouchUpRequest) -> TouchUpResponse:
    """Send touch UP event at specified device coordinates."""
    try:
        from AutoGLM_GUI.adb_plus import touch_up

        touch_up(
            x=request.x,
            y=request.y,
            device_id=request.device_id,
            delay=request.delay,
        )

        return TouchUpResponse(success=True)
    except Exception as e:
        return TouchUpResponse(success=False, error=str(e))
