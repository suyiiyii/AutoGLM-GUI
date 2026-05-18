"""Coverage for ADB/scrcpy boundary code using fakes only."""

from __future__ import annotations

import asyncio
import base64
import socket
import subprocess
from types import SimpleNamespace

import pytest

import AutoGLM_GUI.adb_plus.device as adb_device
import AutoGLM_GUI.adb_plus.ip as adb_ip
import AutoGLM_GUI.adb_plus.keyboard_installer as keyboard
import AutoGLM_GUI.adb_plus.mdns as mdns
import AutoGLM_GUI.adb_plus.pair as pair
import AutoGLM_GUI.adb_plus.qr_pair as qr_pair
import AutoGLM_GUI.adb_plus.screenshot as screenshot
import AutoGLM_GUI.adb_plus.touch as touch
import AutoGLM_GUI.adb_plus.version as adb_version
import AutoGLM_GUI.scrcpy_stream as scrcpy_stream
from AutoGLM_GUI.exceptions import DeviceNotAvailableError
from AutoGLM_GUI.scrcpy_protocol import (
    PTS_CONFIG,
    PTS_KEYFRAME,
    SCRCPY_CODEC_H264,
    ScrcpyVideoStreamOptions,
)
from AutoGLM_GUI.scrcpy_stream import ScrcpyStreamer


PNG_1X1_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


async def _noop_sleep(delay: float) -> None:
    return None


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _streamer(**kwargs) -> ScrcpyStreamer:
    return ScrcpyStreamer(device_id="serial-1", **kwargs)


@pytest.fixture(autouse=True)
def fake_scrcpy_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScrcpyStreamer, "_find_scrcpy_server", lambda self: "/server")


def test_scrcpy_port_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(1)
    try:
        assert asyncio.run(scrcpy_stream.is_port_available(port)) is False
    finally:
        sock.close()

    values = iter([False, False, True])

    async def fake_available(port: int, host: str = "127.0.0.1") -> bool:
        return next(values)

    monkeypatch.setattr(scrcpy_stream, "is_port_available", fake_available)
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    assert asyncio.run(
        scrcpy_stream.wait_for_port_release(1234, timeout=1.0, poll_interval=0.0)
    )


def test_scrcpy_start_cleanup_and_server_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamer = _streamer()
    calls: list[list[str]] = []

    async def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _completed()

    async def fake_check(device_id: str | None) -> None:
        calls.append(["check", str(device_id)])

    async def fake_wait(port: int, timeout: float, poll_interval: float):
        return True

    class FakeProcess:
        returncode = None

        def terminate(self) -> None:
            pass

    async def fake_spawn(cmd, capture_output=False):
        calls.append(cmd)
        return FakeProcess()

    monkeypatch.setattr(scrcpy_stream, "run_cmd_silently", fake_run)
    monkeypatch.setattr(scrcpy_stream, "check_device_available", fake_check)
    monkeypatch.setattr(scrcpy_stream, "wait_for_port_release", fake_wait)
    monkeypatch.setattr(scrcpy_stream, "spawn_process", fake_spawn)
    monkeypatch.setattr(scrcpy_stream, "is_windows", lambda: False)
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    async def fake_connect(self):
        self.tcp_socket = FakeSocket()

    monkeypatch.setattr(ScrcpyStreamer, "_connect_socket", fake_connect)

    asyncio.run(streamer.start())

    assert calls[0] == ["check", "serial-1"]
    assert [
        "adb",
        "-s",
        "serial-1",
        "push",
        "/server",
        "/data/local/tmp/scrcpy-server",
    ] in calls
    assert streamer.forward_cleanup_needed is True
    assert any("app_process" in cmd for cmd in calls)


def test_scrcpy_start_failure_and_server_port_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamer = _streamer()

    async def fail_check(device_id: str | None) -> None:
        raise RuntimeError("device gone")

    stopped = False

    def fake_stop() -> None:
        nonlocal stopped
        stopped = True

    monkeypatch.setattr(scrcpy_stream, "check_device_available", fail_check)
    monkeypatch.setattr(streamer, "stop", fake_stop)
    with pytest.raises(RuntimeError, match="Failed to start scrcpy server"):
        asyncio.run(streamer.start())
    assert stopped

    conflict = _streamer()

    class FailedProc:
        returncode = 1

        async def communicate(self):
            return b"", b"Address already in use"

    async def fake_spawn(cmd, capture_output=False):
        return FailedProc()

    monkeypatch.setattr(scrcpy_stream, "spawn_process", fake_spawn)
    monkeypatch.setattr(scrcpy_stream, "is_windows", lambda: False)

    async def cleanup_noop() -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    monkeypatch.setattr(conflict, "_cleanup_existing_server", cleanup_noop)
    with pytest.raises(RuntimeError, match="persistently occupied"):
        asyncio.run(conflict._start_server())
    conflict.scrcpy_process = None


class FakeSocket:
    def __init__(self, data: bytes = b"", fail_connects: int = 0) -> None:
        self.data = bytearray(data)
        self.fail_connects = fail_connects
        self.closed = False
        self.options: list[tuple[int, int, int]] = []

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))

    def settimeout(self, value: float | None) -> None:
        self.timeout = value

    def connect(self, address) -> None:
        if self.fail_connects > 0:
            self.fail_connects -= 1
            raise ConnectionRefusedError("not yet")

    def recv(self, size: int) -> bytes:
        if not self.data:
            return b""
        chunk = bytes(self.data[:size])
        del self.data[:size]
        return chunk

    def close(self) -> None:
        self.closed = True


def test_scrcpy_socket_connect_metadata_packets_and_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeSocket] = []

    def fake_socket(*args, **kwargs):
        sock = FakeSocket(fail_connects=1 if not created else 0)
        created.append(sock)
        return sock

    streamer = _streamer()
    real_socket = socket.socket

    async def run_connect() -> None:
        monkeypatch.setattr(scrcpy_stream.socket, "socket", fake_socket)
        monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
        try:
            await streamer._connect_socket()
        finally:
            monkeypatch.setattr(scrcpy_stream.socket, "socket", real_socket)

    asyncio.run(run_connect())
    assert len(created) == 2
    assert created[0].closed is True
    assert streamer.tcp_socket is created[1]

    name = b"Pixel 8" + b"\x00" * (64 - len("Pixel 8"))
    raw = (
        b"\x00"
        + name
        + SCRCPY_CODEC_H264.to_bytes(4, "big")
        + (1080).to_bytes(4, "big")
        + (2400).to_bytes(4, "big")
        + PTS_CONFIG.to_bytes(8, "big")
        + (3).to_bytes(4, "big")
        + b"cfg"
        + (PTS_KEYFRAME | 12).to_bytes(8, "big")
        + (4).to_bytes(4, "big")
        + b"data"
    )
    packet_streamer = _streamer(
        stream_options=ScrcpyVideoStreamOptions(send_dummy_byte=True)
    )
    packet_streamer.tcp_socket = FakeSocket(raw)

    metadata = asyncio.run(packet_streamer.read_video_metadata())
    config_packet = asyncio.run(packet_streamer.read_media_packet())
    data_packet = asyncio.run(packet_streamer.read_media_packet())

    assert metadata.device_name == "Pixel 8"
    assert metadata.width == 1080
    assert metadata.height == 2400
    assert config_packet.type == "configuration"
    assert data_packet.keyframe is True
    assert data_packet.pts == 12

    no_frame = _streamer(stream_options=ScrcpyVideoStreamOptions(send_frame_meta=False))
    with pytest.raises(RuntimeError, match="send_frame_meta"):
        asyncio.run(no_frame.read_media_packet())

    run_calls: list[list[str]] = []
    packet_streamer.forward_cleanup_needed = True
    monkeypatch.setattr(
        scrcpy_stream.subprocess,
        "run",
        lambda cmd, **kwargs: run_calls.append(cmd),
    )
    packet_streamer.stop()
    assert run_calls[-1][-1] == "tcp:27183"


def test_adb_device_availability(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ok(cmd, *args, **kwargs):
        return _completed(stdout="device\n")

    monkeypatch.setattr(adb_device, "run_cmd_silently", ok)
    asyncio.run(adb_device.check_device_available("serial"))

    async def offline(cmd, *args, **kwargs):
        return _completed(stderr="device offline")

    monkeypatch.setattr(adb_device, "run_cmd_silently", offline)
    with pytest.raises(DeviceNotAvailableError, match="not available"):
        asyncio.run(adb_device.check_device_available("serial"))

    async def timeout(cmd, *args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(adb_device, "run_cmd_silently", timeout)
    with pytest.raises(DeviceNotAvailableError, match="timed out"):
        asyncio.run(adb_device.check_device_available("serial"))

    async def missing(cmd, *args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(adb_device, "run_cmd_silently", missing)
    with pytest.raises(DeviceNotAvailableError, match="ADB executable"):
        asyncio.run(adb_device.check_device_available("serial"))


def test_adb_ip_sync_and_async(monkeypatch: pytest.MonkeyPatch) -> None:
    assert adb_ip._extract_ip("inet 192.168.1.5/24") == "192.168.1.5"
    assert adb_ip._extract_ip("inet 0.0.0.0") is None
    assert adb_ip._build_shell_cmd("adb", "s", ["ip"]) == [
        "adb",
        "-s",
        "s",
        "shell",
        "ip",
    ]

    outputs = iter(
        [
            "8.8.8.8 dev rmnet_data0 src 10.0.0.2\n8.8.8.8 dev wlan0 src 192.168.1.8",
            "inet 192.168.1.9/24",
        ]
    )
    monkeypatch.setattr(adb_ip, "_run", lambda *a, **k: next(outputs))
    assert adb_ip.get_wifi_ip("adb", "serial") == "192.168.1.8"

    monkeypatch.setattr(
        adb_ip, "_run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert adb_ip.get_wifi_ip("adb", "serial") is None

    async_outputs = iter(
        [
            _completed(stdout="8.8.8.8 dev rmnet0 src 10.0.0.1"),
            _completed(stdout="inet 192.168.1.10/24"),
        ]
    )

    async def fake_run(cmd, timeout=5):
        return next(async_outputs)

    monkeypatch.setattr(adb_ip, "run_cmd_silently", fake_run)
    assert asyncio.run(adb_ip.get_wifi_ip_async("adb", "serial")) == "192.168.1.10"


def test_screenshot_sync_async_and_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert screenshot._is_valid_png(PNG_1X1_BYTES)
    assert not screenshot._is_valid_png(b"nope")

    monkeypatch.setattr(
        screenshot.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, PNG_1X1_BYTES, b""),
    )
    captured = screenshot.capture_screenshot("serial", retries=0)
    assert captured.width == 1
    assert captured.height == 1

    monkeypatch.setattr(
        screenshot.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, b"", b"device offline"),
    )
    with pytest.raises(DeviceNotAvailableError):
        screenshot._try_capture("serial", "adb", 1)

    monkeypatch.setattr(
        screenshot.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, b"", b"bad png"),
    )
    fallback = screenshot.capture_screenshot("serial", retries=0)
    assert fallback.width == 1080
    assert fallback.is_sensitive is False

    class AsyncProc:
        returncode = 0

        async def communicate(self):
            return PNG_1X1_BYTES, b""

        def kill(self) -> None:
            pass

    async def fake_create(*args, **kwargs):
        return AsyncProc()

    monkeypatch.setattr(screenshot, "is_windows", lambda: False)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    async_captured = asyncio.run(
        screenshot.capture_screenshot_async("serial", retries=0)
    )
    assert async_captured.width == 1


def test_mdns_pair_touch_version_and_keyboard(monkeypatch: pytest.MonkeyPatch) -> None:
    assert mdns._parse_mdns_line("name\t_adb-tls-connect._tcp\t1.2.3.4:5555") == (
        "name",
        "_adb-tls-connect._tcp",
        "1.2.3.4:5555",
    )
    assert mdns._parse_mdns_line("bad") is None
    assert mdns._parse_address("1.2.3.4:5555") == ("1.2.3.4", 5555)
    assert mdns._parse_address("999.2.3.4:5555") is None

    mdns_output = (
        "List of discovered mdns services\n"
        "adb-dev\t_adb-tls-pairing._tcp\t0.0.0.0:12345\n"
        "adb-dev\t_adb-tls-connect._tcp\t192.168.1.50:34567\n"
    )
    monkeypatch.setattr(
        mdns, "run_cmd_silently_sync", lambda *a, **k: _completed(stdout=mdns_output)
    )
    devices = mdns.discover_mdns_devices()
    assert devices[0].has_pairing is True
    assert devices[0].pairing_port == 12345

    monkeypatch.setattr(
        pair,
        "run_cmd_silently_sync",
        lambda *a, **k: _completed(stdout="Successfully paired"),
    )
    assert pair.pair_device("1.2.3.4", 1234, "123456")[0] is True
    assert pair.pair_device("1.2.3.4", 1234, "bad") == (
        False,
        "Pairing code must be 6 digits",
    )

    async def fake_pair_run(cmd, timeout=30):
        return _completed(stdout="failed: pairing code")

    monkeypatch.setattr(pair, "run_cmd_silently", fake_pair_run)
    assert asyncio.run(pair.pair_device_async("1.2.3.4", 1234, "123456")) == (
        False,
        "Invalid pairing code",
    )

    run_calls: list[list[str]] = []
    monkeypatch.setattr(
        touch.subprocess, "run", lambda cmd, **kwargs: run_calls.append(cmd)
    )
    monkeypatch.setattr(touch.time, "sleep", lambda delay: None)
    touch.touch_down(1, 2, "serial", delay=0.1)
    touch.touch_move(3, 4, "serial")
    touch.touch_up(5, 6, "serial")
    assert [call[-3] for call in run_calls] == ["DOWN", "MOVE", "UP"]

    async_calls: list[list[str]] = []

    async def fake_touch_run(cmd, timeout=5):
        async_calls.append(cmd)
        return _completed()

    monkeypatch.setattr(touch, "run_cmd_silently", fake_touch_run)
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    asyncio.run(touch.touch_down_async(1, 2, "serial", delay=0))
    asyncio.run(touch.touch_move_async(3, 4, "serial", delay=0))
    asyncio.run(touch.touch_up_async(5, 6, "serial", delay=0))
    assert [call[-3] for call in async_calls] == ["DOWN", "MOVE", "UP"]

    monkeypatch.setattr(
        adb_version,
        "run_cmd_silently_sync",
        lambda *a, **k: _completed(stdout="Android Debug Bridge version 1.0.41"),
    )
    assert adb_version.get_adb_version() == (1, 0, 41)
    monkeypatch.setattr(
        adb_version,
        "run_cmd_silently_sync",
        lambda *a, **k: _completed(stdout="Version 34.0.5-11580240"),
    )
    assert adb_version.get_adb_version() == (34, 0, 5)
    monkeypatch.setattr(
        adb_version,
        "run_cmd_silently_sync",
        lambda *a, **k: _completed(stdout="mdns services"),
    )
    assert adb_version.supports_mdns_services()

    installer = keyboard.ADBKeyboardInstaller("serial")
    monkeypatch.setattr(
        installer, "get_apk_path", lambda: SimpleNamespace(exists=lambda: True)
    )
    monkeypatch.setattr(installer, "is_installed", lambda: True)
    monkeypatch.setattr(installer, "is_enabled", lambda: False)
    monkeypatch.setattr(installer, "enable", lambda: (True, "enabled"))
    assert installer.auto_setup() == (True, "enabled")
    status = installer.get_status()
    assert status["status"] == "installed_but_disabled"


def test_qr_pair_listener_and_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeInfo:
        port = 1234
        server = "host.local."

        def __init__(self, addrs: list[str]) -> None:
            self._addrs = addrs

        def parsed_addresses(self) -> list[str]:
            return self._addrs

    assert (
        qr_pair._pick_host_from_info(FakeInfo(["fe80::1", "192.168.1.2"]))
        == "192.168.1.2"
    )
    assert qr_pair._pick_host_from_info(FakeInfo([])) == "host.local"

    monkeypatch.setattr(
        qr_pair,
        "run_cmd_silently_sync",
        lambda cmd, timeout=20: _completed(
            stdout="Successfully paired" if "pair" in cmd else "connected to device"
        ),
    )
    assert qr_pair._adb_pair("1.2.3.4", 1234, "pass")
    assert qr_pair._adb_connect("1.2.3.4", 5555)

    session = qr_pair.PairingSession(
        session_id="sid",
        name="name",
        password="pass",
        qr_payload="payload",
        status="listening",
    )
    listener = qr_pair.QRPairingListener(session, "adb")

    class FakeZeroconf:
        def __init__(self, info: FakeInfo) -> None:
            self.info = info

        def get_service_info(self, type_, name, timeout=3000):
            return self.info

    zc = FakeZeroconf(FakeInfo(["192.168.1.2"]))
    listener.add_service(zc, qr_pair.PAIR_SERVICE_TYPE, "pair")
    listener.add_service(zc, qr_pair.PAIR_SERVICE_TYPE, "pair")
    listener.add_service(zc, qr_pair.CONNECT_SERVICE_TYPE, "connect")
    listener.update_service(zc, qr_pair.CONNECT_SERVICE_TYPE, "connect")
    listener.remove_service(zc, qr_pair.CONNECT_SERVICE_TYPE, "connect")

    assert session.status == "connected"
    assert session.device_id == "192.168.1.2:1234"

    manager = qr_pair.QRPairingManager()
    session.zeroconf = SimpleNamespace(close=lambda: None)
    session.thread = SimpleNamespace(is_alive=lambda: False, join=lambda timeout: None)
    manager._sessions["sid"] = session
    assert manager.get_session("sid") is session
    assert manager.cancel_session("sid") is True
    assert manager.cancel_session("missing") is False
