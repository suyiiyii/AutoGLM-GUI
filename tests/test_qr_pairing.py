"""Unit tests for QR-based wireless ADB pairing."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import pytest

import AutoGLM_GUI.adb_plus.qr_pair as qr_pair


def _session(**kwargs: Any) -> qr_pair.PairingSession:
    defaults = {
        "session_id": "sid",
        "name": "debug-name",
        "password": "password",
        "qr_payload": "payload",
        "status": "listening",
        "expires_at": 9999999999.0,
    }
    defaults.update(kwargs)
    return qr_pair.PairingSession(**defaults)


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["adb"], returncode=returncode, stdout=stdout
    )


def test_pick_host_falls_back_and_handles_errors() -> None:
    class RaisingInfo:
        server = ""

        def parsed_addresses(self) -> list[str]:
            raise RuntimeError("bad addresses")

    assert qr_pair._pick_host_from_info(RaisingInfo()) is None

    class HostOnlyInfo:
        server = "device.local."

        def parsed_addresses(self) -> list[str]:
            raise RuntimeError("bad addresses")

    assert qr_pair._pick_host_from_info(HostOnlyInfo()) == "device.local"


def test_adb_pair_and_connect_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], int]] = []

    def fake_run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, timeout))
        return _completed("failure", returncode=1)

    monkeypatch.setattr(qr_pair, "run_cmd_silently_sync", fake_run)

    assert qr_pair._adb_pair("1.2.3.4", 1234, "pass", "adbx") is False
    assert qr_pair._adb_connect("1.2.3.4", 5555, "adbx") is False
    assert calls == [
        (["adbx", "pair", "1.2.3.4:1234", "pass"], 25),
        (["adbx", "connect", "1.2.3.4:5555"], 20),
    ]


def test_listener_ignores_invalid_services(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session()
    listener = qr_pair.QRPairingListener(session, "adb")

    class FakeZeroconf:
        def __init__(self, info: Any) -> None:
            self.info = info

        def get_service_info(self, type_: str, name: str, timeout: int = 3000) -> Any:
            return self.info

    class NoHostInfo:
        port = 1234
        server = ""

        def parsed_addresses(self) -> list[str]:
            return []

    class NoPortInfo:
        port = None
        server = "host.local."

        def parsed_addresses(self) -> list[str]:
            return []

    listener.add_service(FakeZeroconf(None), qr_pair.PAIR_SERVICE_TYPE, "missing")
    listener.add_service(
        FakeZeroconf(NoHostInfo()), qr_pair.PAIR_SERVICE_TYPE, "nohost"
    )
    listener.add_service(
        FakeZeroconf(NoPortInfo()), qr_pair.PAIR_SERVICE_TYPE, "noport"
    )

    assert session.status == "listening"
    assert listener.attempted_pair == set()


def test_listener_pair_and_connect_negative_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInfo:
        def __init__(self, host: str, port: int = 1234) -> None:
            self.host = host
            self.port = port
            self.server = ""

        def parsed_addresses(self) -> list[str]:
            return [self.host]

    class FakeZeroconf:
        def __init__(self, info: FakeInfo) -> None:
            self.info = info

        def get_service_info(
            self, type_: str, name: str, timeout: int = 3000
        ) -> FakeInfo:
            return self.info

    pair_attempts: list[tuple[str, int, str, str]] = []
    connect_attempts: list[tuple[str, int, str]] = []

    def fake_pair(host: str, port: int, password: str, adb_path: str) -> bool:
        pair_attempts.append((host, port, password, adb_path))
        return False

    def fake_connect(host: str, port: int, adb_path: str) -> bool:
        connect_attempts.append((host, port, adb_path))
        return False

    monkeypatch.setattr(qr_pair, "_adb_pair", fake_pair)
    monkeypatch.setattr(qr_pair, "_adb_connect", fake_connect)

    session = _session()
    listener = qr_pair.QRPairingListener(session, "adbx")
    zc = FakeZeroconf(FakeInfo("192.168.1.2"))

    listener.add_service(zc, qr_pair.PAIR_SERVICE_TYPE, "pair")
    listener.add_service(zc, qr_pair.PAIR_SERVICE_TYPE, "pair")

    assert pair_attempts == [("192.168.1.2", 1234, "password", "adbx")]
    assert listener.paired is False
    assert session.status == "pairing"

    listener.paired = True
    listener.last_paired_host = "192.168.1.99"
    listener.add_service(zc, qr_pair.CONNECT_SERVICE_TYPE, "connect-other-host")
    assert connect_attempts == []

    listener.last_paired_host = "192.168.1.2"
    listener.add_service(zc, qr_pair.CONNECT_SERVICE_TYPE, "connect")
    listener.add_service(zc, qr_pair.CONNECT_SERVICE_TYPE, "connect")

    assert connect_attempts == [("192.168.1.2", 1234, "adbx")]
    assert listener.connected is False
    assert session.status == "connecting"


def test_manager_create_session_builds_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = qr_pair.QRPairingManager()
    started: list[tuple[qr_pair.PairingSession, str]] = []

    monkeypatch.setattr(qr_pair.uuid, "uuid4", lambda: "session-id")
    monkeypatch.setattr(qr_pair.secrets, "token_hex", lambda n: f"hex{n}")
    monkeypatch.setattr(
        manager,
        "_start_listener",
        lambda session, adb_path: started.append((session, adb_path)),
    )

    session = manager.create_session(timeout=30, adb_path="adbx")

    assert session.session_id == "session-id"
    assert session.name == "debug-hex4"
    assert session.password == "hex8"
    assert session.qr_payload == "WIFI:T:ADB;S:debug-hex4;P:hex8;;"
    assert session.status == "listening"
    assert session.expires_at - session.created_at == 30
    assert manager.get_session("session-id") is session
    assert started == [(session, "adbx")]


def test_start_listener_handles_connected_timeout_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeThread:
        def __init__(self, target, name: str, daemon: bool) -> None:
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False

        def start(self) -> None:
            self.started = True
            self.target()

        def is_alive(self) -> bool:
            return False

    class FakeZeroconf:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    def fake_browser(zc: FakeZeroconf, type_: str, listener: Any) -> None:
        if type_ == qr_pair.CONNECT_SERVICE_TYPE:
            listener.connected = True

    monkeypatch.setattr(qr_pair.threading, "Thread", FakeThread)
    monkeypatch.setattr(qr_pair, "Zeroconf", FakeZeroconf)
    monkeypatch.setattr(qr_pair, "ServiceBrowser", fake_browser)

    connected_session = _session(session_id="connected")
    qr_pair.QRPairingManager()._start_listener(connected_session, "adb")
    assert connected_session.thread.started is True
    assert connected_session.status == "listening"
    assert connected_session.zeroconf.closed is True

    def passive_browser(zc: FakeZeroconf, type_: str, listener: Any) -> None:
        return None

    monkeypatch.setattr(qr_pair, "ServiceBrowser", passive_browser)
    timeout_session = _session(session_id="timeout", expires_at=0)
    qr_pair.QRPairingManager()._start_listener(timeout_session, "adb")
    assert timeout_session.status == "timeout"

    class BrokenZeroconf:
        def __init__(self) -> None:
            raise RuntimeError("zeroconf failed")

    monkeypatch.setattr(qr_pair, "Zeroconf", BrokenZeroconf)
    error_session = _session(session_id="error")
    qr_pair.QRPairingManager()._start_listener(error_session, "adb")
    assert error_session.status == "error"
    assert error_session.error_message == "zeroconf failed"

    class ClosingZeroconf(FakeZeroconf):
        def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(qr_pair, "Zeroconf", ClosingZeroconf)
    close_error_session = _session(session_id="close-error", expires_at=0)
    qr_pair.QRPairingManager()._start_listener(close_error_session, "adb")
    assert close_error_session.status == "timeout"


def test_cancel_session_handles_close_errors_and_alive_threads() -> None:
    manager = qr_pair.QRPairingManager()

    class BrokenZeroconf:
        def close(self) -> None:
            raise RuntimeError("close failed")

    class AliveThread:
        def __init__(self) -> None:
            self.joined_with: float | None = None
            self.checks = 0

        def is_alive(self) -> bool:
            self.checks += 1
            return True

        def join(self, timeout: float) -> None:
            self.joined_with = timeout

    thread = AliveThread()
    session = _session(zeroconf=BrokenZeroconf(), thread=thread)
    manager._sessions["sid"] = session

    assert manager.cancel_session("sid") is True
    assert thread.joined_with == 2.0
    assert thread.checks == 2


@pytest.mark.anyio
async def test_cleanup_expired_sessions_cancels_expired_then_propagates_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = qr_pair.QRPairingManager()
    manager._sessions["expired"] = _session(session_id="expired", expires_at=0)
    manager._sessions["active"] = _session(session_id="active", expires_at=9999999999)
    cancelled: list[str] = []
    sleeps = 0

    async def fake_sleep(seconds: int) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(qr_pair.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        manager,
        "cancel_session",
        lambda session_id: cancelled.append(session_id) or True,
    )

    with pytest.raises(asyncio.CancelledError):
        await manager.cleanup_expired_sessions()

    assert cancelled == ["expired"]
