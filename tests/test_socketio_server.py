"""Unit tests for Socket.IO scrcpy stream orchestration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import AutoGLM_GUI.socketio_server as socketio_server
from AutoGLM_GUI.scrcpy_protocol import ScrcpyMediaStreamPacket


@pytest.fixture(autouse=True)
def reset_socketio_state() -> None:
    socketio_server._socket_streamers.clear()
    socketio_server._stream_tasks.clear()
    socketio_server._device_locks.clear()
    yield
    socketio_server._socket_streamers.clear()
    socketio_server._stream_tasks.clear()
    socketio_server._device_locks.clear()


class FakeTask:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeStreamer:
    def __init__(self, device_id: str = "device-1") -> None:
        self.device_id = device_id
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def test_classify_error_variants() -> None:
    assert (
        socketio_server._classify_error(OSError("Address already in use"))["type"]
        == "port_conflict"
    )
    assert (
        socketio_server._classify_error(RuntimeError("Port 27183 occupied"))["type"]
        == "port_conflict"
    )
    assert (
        socketio_server._classify_error(RuntimeError("Device abc not found"))["type"]
        == "device_offline"
    )
    assert (
        socketio_server._classify_error(TimeoutError("timed out"))["type"] == "timeout"
    )
    assert (
        socketio_server._classify_error(RuntimeError("Failed to connect"))["type"]
        == "connection_failed"
    )
    assert socketio_server._classify_error(RuntimeError("boom"))["type"] == "unknown"


def test_stop_streamers_filters_by_device() -> None:
    stale_task = FakeTask()
    kept_task = FakeTask()
    matching = FakeStreamer("device-1")
    other = FakeStreamer("device-2")

    socketio_server._socket_streamers.update(
        {
            "empty": None,  # type: ignore[dict-item]
            "matching": matching,  # type: ignore[dict-item]
            "other": other,  # type: ignore[dict-item]
        }
    )
    socketio_server._stream_tasks.update(
        {
            "matching": stale_task,  # type: ignore[dict-item]
            "other": kept_task,  # type: ignore[dict-item]
        }
    )

    socketio_server.stop_streamers("device-1")

    assert stale_task.cancelled is True
    assert matching.stopped is True
    assert kept_task.cancelled is False
    assert other.stopped is False
    assert "matching" not in socketio_server._socket_streamers
    assert "other" in socketio_server._socket_streamers

    socketio_server.stop_streamers()
    assert kept_task.cancelled is True
    assert other.stopped is True


@pytest.mark.anyio
async def test_disconnect_stops_stream_for_sid() -> None:
    task = FakeTask()
    streamer = FakeStreamer()
    socketio_server._stream_tasks["sid-1"] = task  # type: ignore[assignment]
    socketio_server._socket_streamers["sid-1"] = streamer  # type: ignore[assignment]

    await socketio_server.connect("sid-1", {})
    await socketio_server.disconnect("sid-1")

    assert task.cancelled is True
    assert streamer.stopped is True
    assert socketio_server._stream_tasks == {}
    assert socketio_server._socket_streamers == {}


def test_packet_to_payload_includes_frame_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socketio_server.time, "time", lambda: 12.345)
    payload = socketio_server._packet_to_payload(
        ScrcpyMediaStreamPacket(type="data", data=b"frame", keyframe=True, pts=123)
    )

    assert payload == {
        "type": "data",
        "data": b"frame",
        "timestamp": 12345,
        "keyframe": True,
        "pts": 123,
    }

    config_payload = socketio_server._packet_to_payload(
        ScrcpyMediaStreamPacket(type="config", data=b"cfg")
    )
    assert config_payload == {
        "type": "config",
        "data": b"cfg",
        "timestamp": 12345,
    }


@pytest.mark.anyio
async def test_stream_packets_emits_payloads_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PacketStreamer(FakeStreamer):
        async def iter_packets(self):
            yield ScrcpyMediaStreamPacket(type="data", data=b"abc")

    emitted: list[tuple[str, dict[str, Any], str]] = []

    async def fake_emit(event: str, payload: dict[str, Any], to: str) -> None:
        emitted.append((event, payload, to))

    task = FakeTask()
    streamer = PacketStreamer()
    socketio_server._stream_tasks["sid-1"] = task  # type: ignore[assignment]
    socketio_server._socket_streamers["sid-1"] = streamer  # type: ignore[assignment]
    monkeypatch.setattr(socketio_server.sio, "emit", fake_emit)

    await socketio_server._stream_packets("sid-1", streamer)  # type: ignore[arg-type]

    assert emitted[0][0] == "video-data"
    assert emitted[0][1]["data"] == b"abc"
    assert emitted[0][2] == "sid-1"
    assert task.cancelled is True
    assert streamer.stopped is True
    assert socketio_server._stream_tasks == {}
    assert socketio_server._socket_streamers == {}


@pytest.mark.anyio
async def test_stream_packets_emits_errors_and_handles_emit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ErrorStreamer(FakeStreamer):
        async def iter_packets(self):
            raise RuntimeError("stream failed")
            yield  # pragma: no cover

    emitted: list[tuple[str, dict[str, Any], str]] = []

    async def fake_emit(event: str, payload: dict[str, Any], to: str) -> None:
        emitted.append((event, payload, to))

    monkeypatch.setattr(socketio_server.sio, "emit", fake_emit)
    await socketio_server._stream_packets("sid-1", ErrorStreamer())  # type: ignore[arg-type]

    assert emitted == [("error", {"message": "stream failed"}, "sid-1")]

    async def failing_emit(event: str, payload: dict[str, Any], to: str) -> None:
        raise RuntimeError("emit failed")

    monkeypatch.setattr(socketio_server.sio, "emit", failing_emit)
    await socketio_server._stream_packets("sid-2", ErrorStreamer())  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_stream_packets_reraises_cancelled_error() -> None:
    class CancelledStreamer(FakeStreamer):
        async def iter_packets(self):
            raise asyncio.CancelledError
            yield  # pragma: no cover

    streamer = CancelledStreamer()
    socketio_server._socket_streamers["sid-1"] = streamer  # type: ignore[assignment]

    with pytest.raises(asyncio.CancelledError):
        await socketio_server._stream_packets("sid-1", streamer)  # type: ignore[arg-type]

    assert streamer.stopped is True


@pytest.mark.anyio
async def test_connect_device_rejects_missing_device_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[tuple[str, dict[str, Any], str]] = []

    async def fake_emit(event: str, payload: dict[str, Any], to: str) -> None:
        emitted.append((event, payload, to))

    monkeypatch.setattr(socketio_server.sio, "emit", fake_emit)

    await socketio_server.connect_device("sid-1", None)

    assert emitted == [
        (
            "error",
            {"message": "Device ID is required", "type": "invalid_request"},
            "sid-1",
        )
    ]


@pytest.mark.anyio
async def test_connect_device_starts_stream_and_replaces_existing_device_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Any] = []

    class StartedStreamer(FakeStreamer):
        def __init__(self, device_id: str, max_size: int, bit_rate: int) -> None:
            super().__init__(device_id)
            self.max_size = max_size
            self.bit_rate = bit_rate
            self.started = False
            created.append(self)

        async def start(self) -> None:
            self.started = True

        async def read_video_metadata(self) -> Any:
            return SimpleNamespace(
                device_name="Pixel",
                width=1080,
                height=2400,
                codec=0x68323634,
            )

    emitted: list[tuple[str, dict[str, Any], str]] = []

    async def fake_emit(event: str, payload: dict[str, Any], to: str) -> None:
        emitted.append((event, payload, to))

    created_tasks: list[Any] = []

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return FakeTask()

    old_task = FakeTask()
    old_streamer = FakeStreamer("device-1")
    socketio_server._stream_tasks["old-sid"] = old_task  # type: ignore[assignment]
    socketio_server._socket_streamers["old-sid"] = old_streamer  # type: ignore[assignment]

    monkeypatch.setattr(socketio_server, "ScrcpyStreamer", StartedStreamer)
    monkeypatch.setattr(socketio_server.sio, "emit", fake_emit)
    monkeypatch.setattr(socketio_server.asyncio, "create_task", fake_create_task)

    await socketio_server.connect_device(
        "sid-1",
        {"deviceId": "device-1", "maxSize": "720", "bitRate": "1000"},
    )

    assert old_task.cancelled is True
    assert old_streamer.stopped is True
    assert created[0].started is True
    assert created[0].max_size == 720
    assert created[0].bit_rate == 1000
    assert emitted == [
        (
            "video-metadata",
            {
                "deviceName": "Pixel",
                "width": 1080,
                "height": 2400,
                "codec": 0x68323634,
            },
            "sid-1",
        )
    ]
    assert socketio_server._socket_streamers["sid-1"] is created[0]
    assert isinstance(socketio_server._stream_tasks["sid-1"], FakeTask)
    assert len(created_tasks) == 1


@pytest.mark.anyio
async def test_connect_device_emits_classified_start_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Any] = []

    class FailingStreamer(FakeStreamer):
        def __init__(self, device_id: str, max_size: int, bit_rate: int) -> None:
            super().__init__(device_id)
            created.append(self)

        async def start(self) -> None:
            raise TimeoutError("startup timeout")

        async def read_video_metadata(self) -> Any:
            raise AssertionError("metadata should not be read")

    emitted: list[tuple[str, dict[str, Any], str]] = []

    async def fake_emit(event: str, payload: dict[str, Any], to: str) -> None:
        emitted.append((event, payload, to))

    monkeypatch.setattr(socketio_server, "ScrcpyStreamer", FailingStreamer)
    monkeypatch.setattr(socketio_server.sio, "emit", fake_emit)

    await socketio_server.connect_device("sid-1", {"device_id": "device-1"})

    assert created[0].stopped is True
    assert emitted[0][0] == "error"
    assert emitted[0][1]["type"] == "timeout"
    assert emitted[0][2] == "sid-1"
