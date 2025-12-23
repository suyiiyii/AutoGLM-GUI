"""Socket.IO server for Scrcpy video streaming."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import socketio

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platforms.adb.video.scrcpy_protocol import ScrcpyMediaStreamPacket
from AutoGLM_GUI.platforms.adb.video.scrcpy_stream import ScrcpyStreamer

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)

_socket_streamers: dict[str, ScrcpyStreamer] = {}
_stream_tasks: dict[str, asyncio.Task] = {}


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


def _packet_to_payload(packet: ScrcpyMediaStreamPacket) -> dict[str, Any]:
    payload: dict[str, Any] = {
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


@sio.on("connect-device")
async def connect_device(sid: str, data: dict | None) -> None:
    payload = data or {}
    device_id = payload.get("device_id") or payload.get("deviceId")
    max_size = int(payload.get("maxSize") or 1280)
    bit_rate = int(payload.get("bitRate") or 4_000_000)

    await _stop_stream_for_sid(sid)

    try:
        from AutoGLM_GUI.state import agent_types, known_device_types

        if (
            device_id
            and (agent_types.get(device_id) or known_device_types.get(device_id))
            == "ios"
        ):
            return
    except Exception:
        pass

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
    except Exception as exc:
        streamer.stop()
        logger.exception("Failed to start scrcpy stream: %s", exc)
        await sio.emit("error", {"message": str(exc)}, to=sid)
        return

    _socket_streamers[sid] = streamer
    _stream_tasks[sid] = asyncio.create_task(_stream_packets(sid, streamer))
