"""Media routes: screenshot, video stream, stream reset."""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from AutoGLM_GUI.adb_plus import capture_screenshot
from AutoGLM_GUI.schemas import ScreenshotRequest, ScreenshotResponse
from AutoGLM_GUI.scrcpy_stream import ScrcpyStreamer
from AutoGLM_GUI.state import scrcpy_locks, scrcpy_streamers

router = APIRouter()

# Debug configuration: Set DEBUG_SAVE_VIDEO_STREAM=1 to save streams to debug_streams/
DEBUG_SAVE_STREAM = os.getenv("DEBUG_SAVE_VIDEO_STREAM", "0") == "1"


@router.post("/api/video/reset")
async def reset_video_stream(device_id: str | None = None) -> dict:
    """Reset video stream (cleanup scrcpy server，多设备支持)."""
    if device_id:
        if device_id in scrcpy_locks:
            async with scrcpy_locks[device_id]:
                if device_id in scrcpy_streamers:
                    print(f"[video/reset] Stopping streamer for device {device_id}")
                    scrcpy_streamers[device_id].stop()
                    del scrcpy_streamers[device_id]
                    print(f"[video/reset] Streamer reset for device {device_id}")
                    return {
                        "success": True,
                        "message": f"Video stream reset for device {device_id}",
                    }
                return {
                    "success": True,
                    "message": f"No active video stream for device {device_id}",
                }
        return {"success": True, "message": f"No video stream for device {device_id}"}

    device_ids = list(scrcpy_streamers.keys())
    for dev_id in device_ids:
        if dev_id in scrcpy_locks:
            async with scrcpy_locks[dev_id]:
                if dev_id in scrcpy_streamers:
                    scrcpy_streamers[dev_id].stop()
                    del scrcpy_streamers[dev_id]
    print("[video/reset] All streamers reset")
    return {"success": True, "message": "All video streams reset"}


@router.post("/api/screenshot", response_model=ScreenshotResponse)
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


@router.websocket("/api/video/stream")
async def video_stream_ws(
    websocket: WebSocket,
    device_id: str | None = None,
):
    """Stream real-time H.264 video from scrcpy server via WebSocket（多设备支持）."""
    await websocket.accept()

    if not device_id:
        await websocket.send_json({"error": "device_id is required"})
        return

    print(f"[video/stream] WebSocket connection for device {device_id}")

    # Debug: Save stream to file for analysis (controlled by DEBUG_SAVE_VIDEO_STREAM env var)
    debug_file = None
    if DEBUG_SAVE_STREAM:
        debug_dir = Path("debug_streams")
        debug_dir.mkdir(exist_ok=True)
        debug_file_path = (
            debug_dir / f"{device_id}_{int(__import__('time').time())}.h264"
        )
        debug_file = open(debug_file_path, "wb")
        print(f"[video/stream] DEBUG: Saving stream to {debug_file_path}")

    if device_id not in scrcpy_locks:
        scrcpy_locks[device_id] = asyncio.Lock()

    async with scrcpy_locks[device_id]:
        if device_id not in scrcpy_streamers:
            print(f"[video/stream] Creating streamer for device {device_id}")
            scrcpy_streamers[device_id] = ScrcpyStreamer(
                device_id=device_id, max_size=1280, bit_rate=4_000_000
            )

            try:
                print(f"[video/stream] Starting scrcpy server for device {device_id}")
                await scrcpy_streamers[device_id].start()
                print(f"[video/stream] Scrcpy server started for device {device_id}")

                # Read NAL units until we have SPS, PPS, and IDR
                streamer = scrcpy_streamers[device_id]

                print("[video/stream] Reading NAL units for initialization...")
                for attempt in range(20):  # Max 20 NAL units for initialization
                    try:
                        nal_unit = await streamer.read_nal_unit(auto_cache=True)
                        nal_type = nal_unit[4] & 0x1F if len(nal_unit) > 4 else -1
                        nal_type_names = {5: "IDR", 7: "SPS", 8: "PPS"}
                        print(
                            f"[video/stream] Read NAL unit: type={nal_type_names.get(nal_type, nal_type)}, size={len(nal_unit)} bytes"
                        )

                        # Check if we have all required parameter sets
                        if (
                            streamer.cached_sps
                            and streamer.cached_pps
                            and streamer.cached_idr
                        ):
                            print(
                                f"[video/stream] ✓ Initialization complete: SPS={len(streamer.cached_sps)}B, PPS={len(streamer.cached_pps)}B, IDR={len(streamer.cached_idr)}B"
                            )
                            break
                    except Exception as e:
                        print(f"[video/stream] Failed to read NAL unit: {e}")
                        await asyncio.sleep(0.5)
                        continue

                # Get initialization data (SPS + PPS + IDR)
                init_data = streamer.get_initialization_data()
                if not init_data:
                    raise RuntimeError(
                        "Failed to get initialization data (missing SPS/PPS/IDR)"
                    )

                # Send initialization data as ONE message (SPS+PPS+IDR combined)
                await websocket.send_bytes(init_data)
                print(
                    f"[video/stream] ✓ Sent initialization data to first client: {len(init_data)} bytes total"
                )

                # Debug: Save to file
                if debug_file:
                    debug_file.write(init_data)
                    debug_file.flush()

            except Exception as e:
                import traceback

                print(f"[video/stream] Failed to start streamer: {e}")
                print(f"[video/stream] Traceback:\n{traceback.format_exc()}")
                scrcpy_streamers[device_id].stop()
                del scrcpy_streamers[device_id]
                try:
                    await websocket.send_json({"error": str(e)})
                except Exception:
                    pass
                return
        else:
            print(f"[video/stream] Reusing streamer for device {device_id}")

            streamer = scrcpy_streamers[device_id]
            # CRITICAL: Send complete initialization data (SPS+PPS+IDR)
            # Without IDR frame, decoder cannot start and will show black screen

            # Wait for initialization data to be ready (max 5 seconds)
            init_data = None
            for attempt in range(10):
                init_data = streamer.get_initialization_data()
                if init_data:
                    break
                print(
                    f"[video/stream] Waiting for initialization data (attempt {attempt + 1}/10)..."
                )
                await asyncio.sleep(0.5)

            if init_data:
                # Log what we're sending
                print(
                    f"[video/stream] ✓ Sending cached initialization data for device {device_id}:"
                )
                print(
                    f"  - SPS: {len(streamer.cached_sps) if streamer.cached_sps else 0}B"
                )
                print(
                    f"  - PPS: {len(streamer.cached_pps) if streamer.cached_pps else 0}B"
                )
                print(
                    f"  - IDR: {len(streamer.cached_idr) if streamer.cached_idr else 0}B"
                )
                print(f"  - Total: {len(init_data)} bytes")

                await websocket.send_bytes(init_data)
                print("[video/stream] ✓ Initialization data sent successfully")

                # Debug: Save to file
                if debug_file:
                    debug_file.write(init_data)
                    debug_file.flush()
            else:
                error_msg = f"Initialization data not ready for device {device_id} after 5 seconds"
                print(f"[video/stream] ERROR: {error_msg}")
                try:
                    await websocket.send_json({"error": error_msg})
                except Exception:
                    pass
                return

    streamer = scrcpy_streamers[device_id]

    stream_failed = False
    try:
        nal_count = 0
        while True:
            try:
                # Read one complete NAL unit
                # Each WebSocket message = one complete NAL unit (clear semantic boundary)
                nal_unit = await streamer.read_nal_unit(auto_cache=True)
                await websocket.send_bytes(nal_unit)

                # Debug: Save to file
                if debug_file:
                    debug_file.write(nal_unit)
                    debug_file.flush()

                nal_count += 1
                if nal_count % 100 == 0:
                    print(
                        f"[video/stream] Device {device_id}: Sent {nal_count} NAL units"
                    )
            except ConnectionError as e:
                print(f"[video/stream] Device {device_id}: Connection error: {e}")
                stream_failed = True
                try:
                    await websocket.send_json({"error": f"Stream error: {str(e)}"})
                except Exception:
                    pass
                break

    except WebSocketDisconnect:
        print(f"[video/stream] Device {device_id}: Client disconnected")
    except Exception as e:
        import traceback

        print(f"[video/stream] Device {device_id}: Error: {e}")
        print(f"[video/stream] Traceback:\n{traceback.format_exc()}")
        stream_failed = True
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass

    if stream_failed:
        async with scrcpy_locks[device_id]:
            if device_id in scrcpy_streamers:
                print(f"[video/stream] Resetting streamer for device {device_id}")
                scrcpy_streamers[device_id].stop()
                del scrcpy_streamers[device_id]

    # Debug: Close file
    if debug_file:
        debug_file.close()
        print("[video/stream] DEBUG: Closed debug file")

    print(f"[video/stream] Device {device_id}: Stream ended")
