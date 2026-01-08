"""Socket.IO server for Scrcpy video streaming."""

from __future__ import annotations

import asyncio
import time

from typing_extensions import NotRequired, TypedDict

import socketio

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.scrcpy_protocol import ScrcpyMediaStreamPacket
from AutoGLM_GUI.scrcpy_stream import ScrcpyStreamer


class VideoPacketPayload(TypedDict):
    type: str
    data: bytes
    timestamp: int
    keyframe: NotRequired[bool | None]
    pts: NotRequired[int | None]


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    server_kwargs={"socketio_path": "/socket.io"},
)

_socket_streamers: dict[str, ScrcpyStreamer] = {}
_stream_tasks: dict[str, asyncio.Task] = {}
_device_locks: dict[str, asyncio.Lock] = {}  # Lock per device to prevent concurrent connections


async def _stop_stream_for_sid(sid: str) -> None:
    task = _stream_tasks.pop(sid, None)
    if task:
        task.cancel()

    streamer = _socket_streamers.pop(sid, None)
    if streamer:
        streamer.stop()


def stop_streamers(device_id: str | None = None) -> None:
    """Stop active scrcpy streamers (all or by device)."""
    sids = list(_socket_streamers.keys())
    for sid in sids:
        streamer = _socket_streamers.get(sid)
        if not streamer:
            continue
        if device_id and streamer.device_id != device_id:
            continue
        task = _stream_tasks.pop(sid, None)
        if task:
            task.cancel()
        streamer.stop()
        _socket_streamers.pop(sid, None)


async def _stream_packets(sid: str, streamer: ScrcpyStreamer) -> None:
    try:
        async for packet in streamer.iter_packets():
            payload = _packet_to_payload(packet)
            await sio.emit("video-data", payload, to=sid)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Video streaming failed: %s", exc)
        try:
            await sio.emit("error", {"message": str(exc)}, to=sid)
        except Exception:
            pass
    finally:
        await _stop_stream_for_sid(sid)


def _packet_to_payload(packet: ScrcpyMediaStreamPacket) -> VideoPacketPayload:
    payload: VideoPacketPayload = {
        "type": packet.type,
        "data": packet.data,
        "timestamp": int(time.time() * 1000),
    }
    if packet.type == "data":
        payload["keyframe"] = packet.keyframe
        payload["pts"] = packet.pts
    return payload


@sio.event
async def connect(sid: str, environ: dict) -> None:
    logger.info("Socket.IO client connected: %s", sid)


@sio.event
async def disconnect(sid: str) -> None:
    logger.info("Socket.IO client disconnected: %s", sid)
    await _stop_stream_for_sid(sid)


@sio.on("connect-device")  # type: ignore[misc]
async def connect_device(sid: str, data: dict | None) -> None:
    payload = data or {}
    device_id = payload.get("device_id") or payload.get("deviceId")
    max_size = int(payload.get("maxSize") or 1280)
    bit_rate = int(payload.get("bitRate") or 4_000_000)

    # Stop any existing stream for this sid
    await _stop_stream_for_sid(sid)

    # Get or create a lock for this device
    if device_id not in _device_locks:
        _device_locks[device_id] = asyncio.Lock()

    device_lock = _device_locks[device_id]

    # Acquire lock to prevent concurrent connections to the same device
    async with device_lock:
        logger.debug(f"Acquired device lock for {device_id}, sid: {sid}")

        # Stop any existing streams for the same device (from other sids)
        sids_to_stop = [
            s
            for s, streamer in _socket_streamers.items()
            if s != sid and streamer.device_id == device_id
        ]
        for s in sids_to_stop:
            logger.info(f"Stopping existing stream for device {device_id} from sid {s}")
            await _stop_stream_for_sid(s)

        max_retries = 3
        retry_delay = 2.0

        last_error: Exception | None = None
        for attempt in range(max_retries):
            streamer = ScrcpyStreamer(
                device_id=device_id,
                max_size=max_size,
                bit_rate=bit_rate,
            )

            try:
                await streamer.start()
                metadata = await streamer.read_video_metadata()
                await sio.emit(
                    "video-metadata",
                    {
                        "deviceName": metadata.device_name,
                        "width": metadata.width,
                        "height": metadata.height,
                        "codec": metadata.codec,
                    },
                    to=sid,
                )

                _socket_streamers[sid] = streamer
                _stream_tasks[sid] = asyncio.create_task(_stream_packets(sid, streamer))
                return

            except Exception as exc:
                last_error = exc
                streamer.stop()

                # Enhanced error reporting - classify error types
                error_type = "unknown"
                user_message = str(exc)

                if "Address already in use" in str(exc) or "Port" in str(exc) and "occupied" in str(exc):
                    error_type = "port_conflict"
                    user_message = (
                        "Port conflict detected. The video stream port is still occupied. "
                        "This usually resolves automatically. If it persists, please restart the app."
                    )
                elif "Device" in str(exc) and ("not available" in str(exc) or "not found" in str(exc)):
                    error_type = "device_offline"
                    user_message = "Device is not responding. Please check USB/WiFi connection."
                elif "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                    error_type = "timeout"
                    user_message = "Connection timed out. Please check device connection and try again."
                elif "Failed to connect" in str(exc):
                    error_type = "connection_failed"
                    user_message = "Failed to connect to scrcpy server. Please check device connection."

                if attempt < max_retries - 1:
                    logger.warning(
                        "Failed to connect scrcpy (attempt %d/%d, type=%s): %s. Retrying in %ss...",
                        attempt + 1,
                        max_retries,
                        error_type,
                        exc,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.exception(
                        "Failed to start scrcpy stream after %d attempts (type=%s)",
                        max_retries,
                        error_type,
                    )

        if last_error:
            # Structured error with type and user-friendly message
            await sio.emit(
                "error",
                {
                    "message": user_message,
                    "type": error_type,
                    "technical_details": str(last_error),
                },
                to=sid,
            )
