"""Coverage for ADB/scrcpy boundary code using fakes only."""

from __future__ import annotations

import asyncio
import base64
import socket
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

import AutoGLM_GUI.adb.apps as adb_apps
import AutoGLM_GUI.adb.connection as adb_connection
import AutoGLM_GUI.adb.device as adb_core_device
import AutoGLM_GUI.adb.input as adb_input
import AutoGLM_GUI.adb_plus.device as adb_device
import AutoGLM_GUI.adb_plus.display as adb_display
import AutoGLM_GUI.adb_plus.ip as adb_ip
import AutoGLM_GUI.adb_plus.keyboard_installer as keyboard
import AutoGLM_GUI.adb_plus.mdns as mdns
import AutoGLM_GUI.adb_plus.pair as pair
import AutoGLM_GUI.adb_plus.qr_pair as qr_pair
import AutoGLM_GUI.adb_plus.screenshot as screenshot
import AutoGLM_GUI.adb_plus.touch as touch
import AutoGLM_GUI.adb_plus.version as adb_version
import AutoGLM_GUI.devices.adb_device as adb_device_impl
import AutoGLM_GUI.platform_utils as platform_utils
import AutoGLM_GUI.scrcpy_stream as scrcpy_stream
from AutoGLM_GUI.exceptions import DeviceNotAvailableError
from AutoGLM_GUI.adb_plus.display import DisplaySelection
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

    async def fake_select_display(device_id: str | None):
        return DisplaySelection("0", "physical-0", 1200, 2608, "test")

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
    monkeypatch.setattr(
        scrcpy_stream, "select_primary_display_async", fake_select_display
    )
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
    server_cmd = next(cmd for cmd in calls if "app_process" in cmd)
    assert "display_id=0" in server_cmd


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


def test_adb_connection_command_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    assert adb_connection.is_adb_tcpip_device_id("192.168.1.2:5555")
    assert not adb_connection.is_adb_tcpip_device_id("usb-1")
    assert (
        adb_connection.infer_connection_type_from_device_id("192.168.1.2:5555")
        == adb_connection.ConnectionType.REMOTE
    )
    assert (
        adb_connection.infer_connection_type_from_device_id("usb-1")
        == adb_connection.ConnectionType.USB
    )

    conn = adb_connection.ADBConnection("adbx")
    run_calls: list[list[str]] = []

    def fake_connect_run(cmd, **kwargs):
        run_calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, stdout="connected to device", stderr=""
        )

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_connect_run)
    assert conn.connect("1.2.3.4") == (True, "Connected to 1.2.3.4:5555")
    assert run_calls[-1] == ["adbx", "connect", "1.2.3.4:5555"]

    def fake_already_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="already connected", stderr=""
        )

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_already_run)
    assert conn.connect("1.2.3.4:7777") == (True, "Connected to 1.2.3.4:7777")

    def fake_failed_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="refused")

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_failed_run)
    assert conn.connect("1.2.3.4:7777") == (False, "refused")
    assert conn.disconnect("1.2.3.4:7777") == (True, "refused")

    def fake_timeout_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_timeout_run)
    assert conn.connect("1.2.3.4:7777", timeout=2) == (
        False,
        "Connection timeout after 2s",
    )

    def fake_broken_run(cmd, **kwargs):
        raise RuntimeError("subprocess failed")

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_broken_run)
    assert conn.connect("1.2.3.4:7777") == (
        False,
        "Connection error: subprocess failed",
    )
    assert conn.disconnect() == (False, "Disconnect error: subprocess failed")

    devices_output = (
        "List of devices attached\n"
        "usb-1 device product:p model:Pixel device:d\n"
        "192.168.1.2:5555 offline product:p model:Remote device:d\n"
    )

    def fake_devices_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=devices_output, stderr="")

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_devices_run)
    listed = conn.list_devices()
    assert [device.device_id for device in listed] == ["usb-1", "192.168.1.2:5555"]
    assert listed[0].model == "Pixel"
    assert listed[1].connection_type == adb_connection.ConnectionType.REMOTE
    assert conn.get_device_info("usb-1") == listed[0]
    assert conn.get_device_info("missing") is None
    assert conn.is_connected("usb-1") is True
    assert conn.is_connected("192.168.1.2:5555") is False
    assert conn.is_connected() is True

    monkeypatch.setattr(
        conn,
        "list_devices",
        lambda: [],
    )
    assert conn.get_device_info() is None
    assert conn.is_connected() is False

    monkeypatch.setattr(adb_connection.time, "sleep", lambda delay: None)

    def fake_tcpip_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="restarting in TCP mode", stderr=""
        )

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_tcpip_run)
    assert conn.enable_tcpip(5556, "usb-1") == (
        True,
        "TCP/IP mode enabled on port 5556",
    )

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_failed_run)
    assert conn.enable_tcpip()[0] is False

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_broken_run)
    assert conn.enable_tcpip() == (False, "Error enabling TCP/IP: subprocess failed")

    monkeypatch.setattr(adb_connection, "get_wifi_ip", lambda **kwargs: "192.168.1.9")
    assert conn.get_device_ip("usb-1") == "192.168.1.9"

    def fake_restart_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(adb_connection.subprocess, "run", fake_restart_run)
    assert conn.restart_server() == (True, "ADB server restarted")
    monkeypatch.setattr(adb_connection.subprocess, "run", fake_broken_run)
    assert conn.restart_server() == (
        False,
        "Error restarting server: subprocess failed",
    )


def test_adb_core_device_command_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    sleeps: list[tuple[str, float]] = []
    current_stdout = {"value": "mCurrentFocus Window{u0 com.tencent.mm/.Main}"}

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "dumpsys" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=current_stdout["value"], stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(adb_core_device.subprocess, "run", fake_run)
    monkeypatch.setattr(
        adb_core_device,
        "trace_sleep",
        lambda delay, name, attrs: sleeps.append((name, delay)),
    )

    assert adb_core_device.get_current_app("serial") == "微信"
    current_stdout["value"] = "mFocusedApp ActivityRecord{u0 unknown.package/.Main}"
    assert adb_core_device.get_current_app("serial") == "System Home"
    current_stdout["value"] = ""
    with pytest.raises(ValueError, match="No output"):
        adb_core_device.get_current_app("serial")

    adb_core_device.tap(1, 2, "serial", delay=0.01)
    adb_core_device.double_tap(3, 4, "serial", delay=0.02)
    adb_core_device.long_press(5, 6, 700, "serial", delay=0.03)
    adb_core_device.swipe(1, 2, 3, 4, device_id="serial", delay=0.04)
    adb_core_device.swipe(1, 2, 3, 4, duration_ms=250, device_id="serial", delay=0.05)
    adb_core_device.back("serial", delay=0.06)
    adb_core_device.home("serial", delay=0.07)
    assert adb_core_device.launch_app("Settings", "serial", delay=0.08) is True
    assert adb_core_device.launch_app("missing", "serial") is False

    flattened = [" ".join(call) for call in calls]
    assert any("input tap 1 2" in call for call in flattened)
    assert any("input swipe 5 6 5 6 700" in call for call in flattened)
    assert any("input keyevent 4" in call for call in flattened)
    assert any("input keyevent KEYCODE_HOME" in call for call in flattened)
    assert any("monkey -p com.android.settings" in call for call in flattened)
    assert [name for name, _ in sleeps] == [
        "sleep.device_tap_delay",
        "sleep.device_double_tap_interval",
        "sleep.device_double_tap_delay",
        "sleep.device_long_press_delay",
        "sleep.device_swipe_delay",
        "sleep.device_swipe_delay",
        "sleep.device_back_delay",
        "sleep.device_home_delay",
        "sleep.device_launch_delay",
    ]


def test_platform_utils_adb_input_apps_and_version_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert platform_utils.build_adb_command() == ["adb"]
    assert platform_utils.build_adb_command("serial", adb_path="adbx") == [
        "adbx",
        "-s",
        "serial",
    ]
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Windows")
    assert platform_utils.is_windows() is True
    monkeypatch.setattr(platform_utils.platform, "system", lambda: "Darwin")
    assert platform_utils.is_windows() is False

    run_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        run_calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="out", stderr="err")

    monkeypatch.setattr(platform_utils.subprocess, "run", fake_run)
    assert platform_utils.run_cmd_silently_sync(["cmd"]).stdout == "out"

    monkeypatch.setattr(platform_utils, "is_windows", lambda: True)
    assert asyncio.run(platform_utils.run_cmd_silently(["cmd"])).stderr == "err"

    class FakeAsyncProcess:
        returncode = 7

        async def communicate(self):
            return b"async-out", b"async-err"

        def kill(self) -> None:
            self.killed = True

    async def fake_create(*cmd, stdout=None, stderr=None):
        run_calls.append(list(cmd))
        return FakeAsyncProcess()

    monkeypatch.setattr(platform_utils, "is_windows", lambda: False)
    monkeypatch.setattr(platform_utils.asyncio, "create_subprocess_exec", fake_create)
    async_result = asyncio.run(platform_utils.run_cmd_silently(["async-cmd"]))
    assert async_result.returncode == 7
    assert async_result.stdout == "async-out"
    assert (
        asyncio.run(
            platform_utils.spawn_process(["spawn"], capture_output=True)
        ).returncode
        == 7
    )

    monkeypatch.setattr(platform_utils, "is_windows", lambda: True)
    monkeypatch.setattr(
        platform_utils.subprocess,
        "Popen",
        lambda cmd, stdout=None, stderr=None: SimpleNamespace(cmd=cmd),
    )
    assert platform_utils.spawn_process
    assert asyncio.run(platform_utils.spawn_process(["spawn-win"])).cmd == ["spawn-win"]

    input_calls: list[list[str]] = []

    def fake_input_run(cmd, **kwargs):
        input_calls.append(cmd)
        if "default_input_method" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="ime.old/.Keyboard", stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(adb_input.subprocess, "run", fake_input_run)
    adb_input.type_text("")
    adb_input.type_text("hi", "serial")
    adb_input.clear_text("serial")
    assert adb_input.detect_and_set_adb_keyboard("serial") == "ime.old/.Keyboard"
    adb_input.restore_keyboard("ime.old/.Keyboard", "serial")
    flattened = [" ".join(call) for call in input_calls]
    assert any("ADB_INPUT_B64" in call for call in flattened)
    assert any("ADB_CLEAR_TEXT" in call for call in flattened)
    assert any("ime set com.android.adbkeyboard/.AdbIME" in call for call in flattened)
    assert any("ime set ime.old/.Keyboard" in call for call in flattened)

    assert adb_apps.get_package_name("Settings") == "com.android.settings"
    assert adb_apps.get_package_name("missing") is None
    assert adb_apps.get_app_name("com.android.settings") is not None
    assert adb_apps.get_app_name("missing.package") is None
    assert "Settings" in adb_apps.list_supported_apps()

    monkeypatch.setattr(
        adb_version,
        "run_cmd_silently_sync",
        lambda *a, **k: _completed(stdout="bad", returncode=1),
    )
    assert adb_version.get_adb_version() is None
    monkeypatch.setattr(
        adb_version,
        "run_cmd_silently_sync",
        lambda *a, **k: _completed(stdout="no version"),
    )
    assert adb_version.get_adb_version() is None
    monkeypatch.setattr(
        adb_version,
        "run_cmd_silently_sync",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("adb missing")),
    )
    assert adb_version.get_adb_version() is None
    assert adb_version.supports_mdns_services() is False

    monkeypatch.setattr(
        adb_version,
        "run_cmd_silently_sync",
        lambda *a, **k: _completed(stderr="unknown command", returncode=1),
    )
    assert adb_version.supports_mdns_services() is False


def test_adb_device_and_manager_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class FakeScreenshot:
        base64_data = "img"
        width = 100
        height = 200
        is_sensitive = True

    monkeypatch.setattr(
        adb_device_impl.adb,
        "get_screenshot",
        lambda device_id, timeout: FakeScreenshot(),
    )
    for name in [
        "tap",
        "double_tap",
        "long_press",
        "swipe",
        "type_text",
        "clear_text",
        "back",
        "home",
        "restore_keyboard",
    ]:
        monkeypatch.setattr(
            adb_device_impl.adb,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args)),
        )
    monkeypatch.setattr(adb_device_impl.adb, "launch_app", lambda *args: True)
    monkeypatch.setattr(
        adb_device_impl.adb, "get_current_app", lambda device_id: "com.example"
    )
    monkeypatch.setattr(
        adb_device_impl.adb,
        "detect_and_set_adb_keyboard",
        lambda device_id: "ime",
    )

    device = adb_device_impl.ADBDevice("serial")
    assert device.device_id == "serial"
    assert device.get_screenshot(timeout=3).is_sensitive is True
    device.tap(1, 2, delay=0)
    device.double_tap(3, 4)
    device.long_press(5, 6, duration_ms=700)
    device.swipe(1, 2, 3, 4, duration_ms=500)
    device.type_text("hello")
    device.clear_text()
    device.back()
    device.home()
    assert device.launch_app("Settings") is True
    assert device.get_current_app() == "com.example"
    assert device.detect_and_set_adb_keyboard() == "ime"
    device.restore_keyboard("ime")
    assert [call[0] for call in calls] == [
        "tap",
        "double_tap",
        "long_press",
        "swipe",
        "type_text",
        "clear_text",
        "back",
        "home",
        "restore_keyboard",
    ]

    class FakeConnection:
        def __init__(self, adb_path: str = "adb") -> None:
            self.adb_path = adb_path
            self.disconnects: list[str] = []

        def list_devices(self):
            return [
                adb_connection.DeviceInfo(
                    device_id="online",
                    status="device",
                    model="Pixel",
                    connection_type=adb_connection.ConnectionType.USB,
                ),
                adb_connection.DeviceInfo(
                    device_id="offline",
                    status="offline",
                    model=None,
                    connection_type=adb_connection.ConnectionType.REMOTE,
                ),
            ]

        def connect(self, address: str, timeout: int = 10):
            return True, f"connected {address}"

        def disconnect(self, device_id: str):
            self.disconnects.append(device_id)
            return True, f"disconnected {device_id}"

    monkeypatch.setattr(adb_device_impl, "ADBConnection", FakeConnection)
    manager = adb_device_impl.ADBDeviceManager("custom-adb")
    infos = manager.list_devices()
    assert infos[0].status == "online"
    assert infos[0].connection_type == "usb"
    assert manager.get_device("online") is manager.get_device("online")
    with pytest.raises(KeyError, match="not found"):
        manager.get_device("missing")
    with pytest.raises(KeyError, match="offline"):
        manager.get_device("offline")
    assert manager.connect("1.2.3.4") == (True, "connected 1.2.3.4")
    manager._devices["online"] = adb_device_impl.ADBDevice("online")
    assert manager.disconnect("online") == (True, "disconnected online")
    assert "online" not in manager._devices


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


def test_display_selection_parsing_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    adb_display.clear_display_selection_cache()

    dumpsys_display = """
Logical Displays:
  Display 1:
    mDisplayId=1
    mBaseDisplayInfo=DisplayInfo{"Rear", displayId 1, real 976 x 596, state OFF, uniqueId="local:222"}
  Display 0:
    mDisplayId=0
    mBaseDisplayInfo=DisplayInfo{"Built-in Screen", displayId 0, real 1200 x 2608, state ON, uniqueId "local:111"}
"""
    selection = adb_display._select_from_outputs(dumpsys_display, "")
    assert selection == DisplaySelection(
        logical_id="0",
        screencap_id="111",
        width=1200,
        height=2608,
        reason="largest_on_display",
    )

    equal_area = """
  Display 2:
    mDisplayId=2
    mBaseDisplayInfo=DisplayInfo{"External", displayId 2, 1000 x 1000, state ON}
  Display 0:
    mDisplayId=0
    mBaseDisplayInfo=DisplayInfo{"Main", displayId 0, 1000 x 1000, state ON}
"""
    assert adb_display._select_from_outputs(equal_area, "").logical_id == "0"

    multiple_on = """
  Display 0:
    mBaseDisplayInfo=DisplayInfo{"Small", displayId 0, 800 x 600, state ON}
  Display 2:
    mBaseDisplayInfo=DisplayInfo{"Large", displayId 2, 1600 x 900, state ON}
"""
    assert adb_display._select_from_outputs(multiple_on, "").logical_id == "2"

    assert adb_display._select_from_outputs("not display output", "") is None

    now = {"value": 100.0}
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=None):
        calls.append(cmd)
        if "SurfaceFlinger" in cmd:
            return _completed(stdout="")
        return _completed(stdout=dumpsys_display)

    monkeypatch.setattr(adb_display.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(adb_display, "run_cmd_silently_sync", fake_run)

    first = adb_display.select_primary_display("serial", ttl_seconds=60)
    second = adb_display.select_primary_display("serial", ttl_seconds=60)
    assert first == second
    assert len(calls) == 2

    now["value"] = 161.0
    adb_display.select_primary_display("serial", ttl_seconds=60)
    assert len(calls) == 4

    adb_display.clear_display_selection_cache()


def test_screenshot_sync_async_and_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert screenshot._is_valid_png(PNG_1X1_BYTES)
    assert not screenshot._is_valid_png(b"nope")

    monkeypatch.setattr(screenshot, "select_primary_display", lambda *a, **k: None)

    async def no_async_display(*args, **kwargs):
        return None

    monkeypatch.setattr(screenshot, "select_primary_display_async", no_async_display)

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


def test_screenshot_uses_display_id_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = DisplaySelection("0", "111", 1200, 2608, "test")
    monkeypatch.setattr(screenshot, "select_primary_display", lambda *a, **k: selection)

    cleared: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        screenshot,
        "clear_display_selection_cache",
        lambda device_id=None, adb_path="adb": cleared.append((device_id, adb_path)),
    )

    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if "-d" in cmd:
            return subprocess.CompletedProcess(cmd, 1, b"", b"bad display")
        return subprocess.CompletedProcess(cmd, 0, PNG_1X1_BYTES, b"")

    monkeypatch.setattr(screenshot.subprocess, "run", fake_run)
    captured = screenshot.capture_screenshot("serial", retries=0)

    assert captured.width == 1
    assert commands[0][-4:] == ["screencap", "-d", "111", "-p"]
    assert commands[1][-2:] == ["screencap", "-p"]
    assert cleared == [("serial", "adb")]


def test_screenshot_async_uses_display_id(monkeypatch: pytest.MonkeyPatch) -> None:
    selection = DisplaySelection("0", "111", 1200, 2608, "test")

    async def async_display(*args, **kwargs):
        return selection

    monkeypatch.setattr(screenshot, "select_primary_display_async", async_display)
    monkeypatch.setattr(screenshot, "is_windows", lambda: True)

    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, PNG_1X1_BYTES, b"")

    monkeypatch.setattr(screenshot.subprocess, "run", fake_run)

    captured = asyncio.run(screenshot.capture_screenshot_async("serial", retries=0))

    assert captured.width == 1
    assert commands[0][-4:] == ["screencap", "-d", "111", "-p"]


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


def test_adb_keyboard_installer_download_install_enable_and_auto_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    import importlib.resources

    cache_apk = tmp_path / "ADBKeyboard.apk"
    monkeypatch.setattr(keyboard, "USER_CACHE_APK_PATH", cache_apk)
    monkeypatch.setattr(
        importlib.resources,
        "files",
        lambda package: (_ for _ in ()).throw(RuntimeError("no bundle")),
    )
    installer = keyboard.ADBKeyboardInstaller("serial")

    run_results = iter(
        [
            _completed(stdout="package:com.android.adbkeyboard"),
            _completed(stdout=keyboard.ADB_KEYBOARD_IME),
            _completed(stdout=""),
        ]
    )

    async def fake_run(cmd, timeout=30):
        return next(run_results)

    monkeypatch.setattr(keyboard, "run_cmd_silently", fake_run)
    assert installer.is_installed() is True
    assert installer.is_enabled() is True
    assert installer.is_installed() is False

    async def broken_run(cmd, timeout=30):
        raise RuntimeError("adb failed")

    monkeypatch.setattr(keyboard, "run_cmd_silently", broken_run)
    assert installer.is_installed() is False
    assert installer.is_enabled() is False

    cache_apk.write_bytes(b"cached")
    assert installer.get_apk_path() == cache_apk
    assert installer.download_apk() is True

    def fake_urlretrieve(url, path):
        path.write_bytes(b"downloaded")

    monkeypatch.setattr(keyboard.urllib.request, "urlretrieve", fake_urlretrieve)
    assert installer.download_apk(force=True) is True

    def empty_urlretrieve(url, path):
        path.write_bytes(b"")

    monkeypatch.setattr(keyboard.urllib.request, "urlretrieve", empty_urlretrieve)
    assert installer.download_apk(force=True) is False

    def failing_urlretrieve(url, path):
        path.write_bytes(b"partial")
        raise RuntimeError("network failed")

    monkeypatch.setattr(keyboard.urllib.request, "urlretrieve", failing_urlretrieve)
    assert installer.download_apk(force=True) is False
    assert not cache_apk.exists()

    monkeypatch.setattr(installer, "get_apk_path", lambda: cache_apk)
    assert installer.install() == (False, "APK file not found. Please download first.")

    cache_apk.write_bytes(b"apk")

    async def install_ok(cmd, timeout=30):
        return _completed(stdout="Success", returncode=1)

    monkeypatch.setattr(keyboard, "run_cmd_silently", install_ok)
    assert installer.install()[0] is True

    async def install_fail(cmd, timeout=30):
        return _completed(stdout="Failure", stderr="bad", returncode=1)

    monkeypatch.setattr(keyboard, "run_cmd_silently", install_fail)
    assert installer.install()[0] is False

    async def install_broken(cmd, timeout=30):
        raise RuntimeError("install crashed")

    monkeypatch.setattr(keyboard, "run_cmd_silently", install_broken)
    assert installer.install() == (False, "Installation error: install crashed")

    async def enable_ok(cmd, timeout=30):
        return _completed(returncode=0)

    monkeypatch.setattr(keyboard, "run_cmd_silently", enable_ok)
    assert installer.enable() == (True, "ADB Keyboard enabled successfully")

    async def enable_nonzero(cmd, timeout=30):
        return _completed(stdout="no", stderr="permission", returncode=1)

    monkeypatch.setattr(keyboard, "run_cmd_silently", enable_nonzero)
    monkeypatch.setattr(installer, "is_enabled", lambda: True)
    assert installer.enable() == (True, "ADB Keyboard enabled (verified)")

    monkeypatch.setattr(installer, "is_enabled", lambda: False)
    assert installer.enable()[0] is False

    async def enable_broken(cmd, timeout=30):
        raise RuntimeError("enable crashed")

    monkeypatch.setattr(keyboard, "run_cmd_silently", enable_broken)
    assert installer.enable() == (False, "Enable error: enable crashed")

    monkeypatch.setattr(installer, "is_installed", lambda: True)
    monkeypatch.setattr(installer, "is_enabled", lambda: True)
    assert installer.auto_setup()[0] is True

    monkeypatch.setattr(installer, "is_enabled", lambda: False)
    monkeypatch.setattr(installer, "enable", lambda: (True, "enabled"))
    assert installer.auto_setup() == (True, "enabled")

    monkeypatch.setattr(installer, "is_installed", lambda: False)
    monkeypatch.setattr(installer, "download_apk", lambda: False)
    assert installer.auto_setup() == (False, "Failed to download APK")

    checks = iter([False, True])
    enabled_checks = iter([False, True])
    monkeypatch.setattr(installer, "is_installed", lambda: next(checks))
    monkeypatch.setattr(installer, "is_enabled", lambda: next(enabled_checks))
    monkeypatch.setattr(installer, "download_apk", lambda: True)
    monkeypatch.setattr(installer, "install", lambda: (True, "installed"))
    monkeypatch.setattr(installer, "enable", lambda: (True, "enabled"))
    assert installer.auto_setup() == (True, "ADB Keyboard setup completed successfully")

    checks = iter([False, True])
    enabled_checks = iter([False, False])
    monkeypatch.setattr(installer, "is_installed", lambda: next(checks))
    monkeypatch.setattr(installer, "is_enabled", lambda: next(enabled_checks))
    assert installer.auto_setup() == (False, "Setup completed but verification failed")

    class FakeInstaller:
        def __init__(self, device_id=None) -> None:
            self.device_id = device_id

        def auto_setup(self):
            return True, "ok"

        def is_installed(self) -> bool:
            return False

    monkeypatch.setattr(keyboard, "ADBKeyboardInstaller", FakeInstaller)
    assert keyboard.auto_setup_adb_keyboard("serial") == (True, "ok")
    assert keyboard.check_and_suggest_installation() is True


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
