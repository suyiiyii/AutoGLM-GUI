"""Focused edge coverage for scrcpy stream lifecycle and parsing."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

import AutoGLM_GUI.scrcpy_stream as scrcpy_stream
from AutoGLM_GUI.adb_plus.display import DisplaySelection
from AutoGLM_GUI.scrcpy_protocol import (
    SCRCPY_CODEC_H264,
    ScrcpyMediaStreamPacket,
    ScrcpyVideoStreamMetadata,
    ScrcpyVideoStreamOptions,
)
from AutoGLM_GUI.scrcpy_stream import ScrcpyStreamer


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScrcpyStreamer, "_find_scrcpy_server", lambda self: "/server")


def test_find_scrcpy_server_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    instance = object.__new__(ScrcpyStreamer)
    instance.tcp_socket = None
    instance.scrcpy_process = None
    instance.forward_cleanup_needed = False

    bundled = tmp_path / "AutoGLM_GUI" / "resources" / "scrcpy-server-v3.3.3"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("server", encoding="utf-8")
    monkeypatch.setattr(scrcpy_stream.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ScrcpyStreamer._find_scrcpy_server(instance) == str(bundled)

    monkeypatch.delattr(scrcpy_stream.sys, "_MEIPASS", raising=False)
    assert ScrcpyStreamer._find_scrcpy_server(instance).endswith(
        "AutoGLM_GUI/resources/scrcpy-server-v3.3.3"
    )

    env_server = tmp_path / "env-server"
    env_server.write_text("server", encoding="utf-8")
    monkeypatch.setenv("SCRCPY_SERVER_PATH", str(env_server))
    monkeypatch.setattr(scrcpy_stream.Path, "exists", lambda self: False)
    assert ScrcpyStreamer._find_scrcpy_server(instance) == str(env_server)

    monkeypatch.delenv("SCRCPY_SERVER_PATH", raising=False)
    monkeypatch.setattr(
        scrcpy_stream.os.path,
        "exists",
        lambda path: path == "/usr/local/share/scrcpy/scrcpy-server",
    )
    assert (
        ScrcpyStreamer._find_scrcpy_server(instance)
        == "/usr/local/share/scrcpy/scrcpy-server"
    )

    monkeypatch.setattr(scrcpy_stream.os.path, "exists", lambda path: False)
    with pytest.raises(FileNotFoundError, match="scrcpy-server not found"):
        ScrcpyStreamer._find_scrcpy_server(instance)


@pytest.mark.anyio
async def test_port_available_success_and_wait_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await scrcpy_stream.is_port_available(0) is True

    async def unavailable(port: int, host: str) -> bool:
        return False

    monkeypatch.setattr(scrcpy_stream, "is_port_available", unavailable)
    monkeypatch.setattr(scrcpy_stream.time, "time", lambda: 10.0)
    assert (
        await scrcpy_stream.wait_for_port_release(1234, timeout=0.0, poll_interval=0.0)
        is False
    )


@pytest.mark.anyio
async def test_cleanup_existing_server_warns_when_port_stays_busy(
    fake_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> None:
        calls.append(cmd)

    monkeypatch.setattr(scrcpy_stream, "run_cmd_silently", fake_run)

    async def unreleased(*args, **kwargs) -> bool:
        return False

    monkeypatch.setattr(scrcpy_stream, "wait_for_port_release", unreleased)

    streamer = ScrcpyStreamer(device_id="serial", port=27183)
    await streamer._cleanup_existing_server()

    assert calls[-1] == ["adb", "-s", "serial", "forward", "--remove", "tcp:27183"]


@pytest.mark.anyio
async def test_start_server_reports_windows_process_error(
    fake_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailedWindowsProcess:
        def poll(self) -> int:
            return 1

        def communicate(self) -> tuple[bytes, bytes]:
            return b"stdout", b"fatal startup"

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    async def fake_spawn(cmd: list[str], capture_output: bool) -> FailedWindowsProcess:
        return FailedWindowsProcess()

    original_sleep = asyncio.sleep

    monkeypatch.setattr(scrcpy_stream, "spawn_process", fake_spawn)
    monkeypatch.setattr(scrcpy_stream, "is_windows", lambda: True)
    monkeypatch.setattr(scrcpy_stream.asyncio, "sleep", lambda delay: original_sleep(0))

    streamer = ScrcpyStreamer(device_id="serial")
    with pytest.raises(RuntimeError, match="fatal startup"):
        await streamer._start_server()


@pytest.mark.anyio
async def test_start_server_retries_without_display_id(
    fake_server: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailedProcess:
        returncode = 1

        async def communicate(self):
            return b"stdout", b"display not found"

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    class RunningProcess:
        returncode = None

        async def communicate(self):
            return b"", b""

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    commands: list[list[str]] = []

    async def fake_spawn(cmd: list[str], capture_output: bool):
        commands.append(cmd)
        if len(commands) == 1:
            return FailedProcess()
        return RunningProcess()

    cleared: list[str | None] = []
    original_sleep = asyncio.sleep

    monkeypatch.setattr(scrcpy_stream, "spawn_process", fake_spawn)
    monkeypatch.setattr(scrcpy_stream, "is_windows", lambda: False)
    monkeypatch.setattr(scrcpy_stream.asyncio, "sleep", lambda delay: original_sleep(0))
    monkeypatch.setattr(
        scrcpy_stream,
        "clear_display_selection_cache",
        lambda device_id=None: cleared.append(device_id),
    )

    streamer = ScrcpyStreamer(device_id="serial")
    streamer._display_selection = DisplaySelection("0", "111", 1200, 2608, "test")

    await streamer._start_server()

    assert "display_id=0" in commands[0]
    assert all("display_id=0" not in arg for arg in commands[1])
    assert cleared == ["serial"]


@pytest.mark.anyio
async def test_connect_socket_retries_and_reports_failure(
    fake_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingSocket:
        def settimeout(self, timeout: float | None) -> None:
            return None

        def setsockopt(self, level: int, optname: int, value: int) -> None:
            raise OSError("buffer denied")

        def connect(self, address: tuple[str, int]) -> None:
            raise ConnectionRefusedError("closed")

        def close(self) -> None:
            raise RuntimeError("close failed")

    original_sleep = asyncio.sleep

    monkeypatch.setattr(scrcpy_stream.socket, "socket", lambda *a, **k: FailingSocket())
    monkeypatch.setattr(scrcpy_stream.asyncio, "sleep", lambda delay: original_sleep(0))

    streamer = ScrcpyStreamer(device_id="serial")
    with pytest.raises(ConnectionError, match="Failed to connect"):
        await streamer._connect_socket()


@pytest.mark.anyio
async def test_read_exactly_errors(fake_server: None) -> None:
    streamer = ScrcpyStreamer(device_id="serial")
    with pytest.raises(ConnectionError, match="Socket not connected"):
        await streamer._read_exactly(1)

    class ClosedSocket:
        def recv(self, size: int) -> bytes:
            return b""

        def close(self) -> None:
            return None

    streamer.tcp_socket = ClosedSocket()  # type: ignore[assignment]
    with pytest.raises(ConnectionError, match="Socket closed by remote"):
        await streamer._read_exactly(1)


class BufferSocket:
    def __init__(self, data: bytes) -> None:
        self.data = bytearray(data)

    def recv(self, size: int) -> bytes:
        chunk = bytes(self.data[:size])
        del self.data[:size]
        return chunk

    def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_metadata_cache_and_legacy_parsing(fake_server: None) -> None:
    streamer = ScrcpyStreamer(device_id="serial")
    streamer._metadata = ScrcpyVideoStreamMetadata(
        device_name="cached", width=1, height=2, codec=SCRCPY_CODEC_H264
    )
    assert await streamer.read_video_metadata() is streamer._metadata

    name = b"Pixel" + b"\x00" * 59
    legacy_size = (1080 << 16) | 2400
    legacy = ScrcpyStreamer(device_id="serial")
    legacy.stream_options = ScrcpyVideoStreamOptions(send_dummy_byte=False)
    legacy.tcp_socket = BufferSocket(name + legacy_size.to_bytes(4, "big"))  # type: ignore[assignment]

    metadata = await legacy.read_video_metadata()
    assert metadata.device_name == "Pixel"
    assert metadata.width == 1080
    assert metadata.height == 2400

    no_codec = ScrcpyStreamer(device_id="serial")
    no_codec.stream_options = ScrcpyVideoStreamOptions(
        send_dummy_byte=False, send_codec_meta=False
    )
    no_codec.tcp_socket = BufferSocket(
        name + (720).to_bytes(2, "big") + (1280).to_bytes(2, "big")
    )  # type: ignore[assignment]
    metadata = await no_codec.read_video_metadata()
    assert metadata.width == 720
    assert metadata.height == 1280


@pytest.mark.anyio
async def test_read_media_packet_initializes_metadata_and_iterates(
    fake_server: None,
) -> None:
    streamer = ScrcpyStreamer(device_id="serial")
    streamer.stream_options = ScrcpyVideoStreamOptions(
        send_dummy_byte=False,
        send_device_meta=False,
        send_codec_meta=False,
    )
    streamer.tcp_socket = BufferSocket(
        (7).to_bytes(8, "big") + (3).to_bytes(4, "big") + b"abc"
    )  # type: ignore[assignment]

    packet = await streamer.read_media_packet()
    assert packet == ScrcpyMediaStreamPacket(
        type="data", data=b"abc", keyframe=False, pts=7
    )

    iterator = ScrcpyStreamer(device_id="serial")
    expected = ScrcpyMediaStreamPacket(type="configuration", data=b"cfg")

    async def fake_read_packet() -> ScrcpyMediaStreamPacket:
        return expected

    iterator.read_media_packet = fake_read_packet  # type: ignore[method-assign]
    agen = iterator.iter_packets()
    assert await agen.__anext__() is expected
    await agen.aclose()


def test_stop_handles_cleanup_errors(
    fake_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BadSocket:
        def close(self) -> None:
            raise OSError("socket close failed")

    class FakePopen:
        def terminate(self) -> None:
            return None

        def wait(self, timeout: float) -> None:
            raise subprocess.TimeoutExpired("scrcpy", timeout)

        def kill(self) -> None:
            raise OSError("kill failed")

    def failing_run(*args, **kwargs) -> None:
        raise subprocess.SubprocessError("forward cleanup failed")

    monkeypatch.setattr(scrcpy_stream.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(scrcpy_stream.subprocess, "run", failing_run)

    streamer = ScrcpyStreamer(device_id="serial")
    streamer.tcp_socket = BadSocket()  # type: ignore[assignment]
    streamer.scrcpy_process = FakePopen()  # type: ignore[assignment]
    streamer.forward_cleanup_needed = True

    streamer.stop()

    assert streamer.tcp_socket is None
    assert streamer.scrcpy_process is None
    assert streamer.forward_cleanup_needed is False
