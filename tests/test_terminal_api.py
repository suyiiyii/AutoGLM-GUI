"""Contract tests for web terminal API endpoints."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.terminal as terminal_api

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeTerminalSession:
    def __init__(self) -> None:
        self.session_id = "terminal-1"
        self.cwd = "/tmp"
        self.command = ["/bin/zsh", "-i"]
        self.status = "running"
        self.created_at = 1700000000.0
        self.last_active_at = 1700000001.0
        self.exit_code: int | None = None
        self.created_by = "127.0.0.1"
        self.origin = "http://localhost:3000"
        self.owner_token_hash = "token-hash"
        self.total_output_bytes = 7
        self.backlog = [
            {"type": "status", "status": "running"},
            {"type": "output", "stream": "stdout", "data": "ready\r\n"},
        ]
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.inputs: list[str] = []
        self.resizes: list[tuple[int, int]] = []
        self.unsubscribed = False

    def to_response(self) -> dict:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "command": self.command,
            "status": self.status,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "exit_code": self.exit_code,
            "created_by": self.created_by,
            "origin": self.origin,
            "owner_token_hash": self.owner_token_hash,
            "total_output_bytes": self.total_output_bytes,
        }

    def subscribe(self) -> tuple[asyncio.Queue[dict], list[dict]]:
        return self.queue, list(self.backlog)

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        assert queue is self.queue
        self.unsubscribed = True

    async def write(self, data: str) -> None:
        self.inputs.append(data)

    async def resize(self, cols: int, rows: int) -> None:
        self.resizes.append((cols, rows))


class FakeTerminalManager:
    def __init__(self) -> None:
        self.session = FakeTerminalSession()
        self.session_token = "token-1"
        self.create_args: tuple[str | None, list[str] | None] | None = None
        self.closed_ids: list[str] = []

    async def create_session(
        self,
        *,
        cwd: str | None = None,
        command: list[str] | None = None,
        created_by: str | None = None,
        origin: str | None = None,
    ) -> tuple[FakeTerminalSession, str]:
        self.create_args = (cwd, command)
        self.session.created_by = created_by or self.session.created_by
        self.session.origin = origin or self.session.origin
        return self.session, self.session_token

    def get_session(self, session_id: str) -> FakeTerminalSession | None:
        if session_id == self.session.session_id:
            return self.session
        return None

    def authenticate_session(
        self, session_id: str, session_token: str | None
    ) -> FakeTerminalSession | None:
        if (
            session_id == self.session.session_id
            and session_token == self.session_token
        ):
            return self.session
        return None

    async def close_session(self, session_id: str) -> bool:
        if session_id != self.session.session_id:
            return False
        self.closed_ids.append(session_id)
        return True


@pytest.fixture
def terminal_env(monkeypatch: pytest.MonkeyPatch) -> dict:
    manager = FakeTerminalManager()
    monkeypatch.setattr(terminal_api, "terminal_session_manager", manager)

    app = FastAPI()
    app.include_router(terminal_api.router)
    client = TestClient(app)

    return {
        "manager": manager,
        "session": manager.session,
        "client": client,
    }


def test_create_terminal_session(terminal_env: dict) -> None:
    response = terminal_env["client"].post("/api/terminal/sessions", json={})

    assert response.status_code == 200
    assert terminal_env["manager"].create_args == (None, None)
    assert response.json()["session_id"] == "terminal-1"
    assert response.json()["session_token"] == "token-1"
    assert response.json()["status"] == "running"


def test_get_terminal_session_not_found(terminal_env: dict) -> None:
    response = terminal_env["client"].get(
        "/api/terminal/sessions/missing",
        params={"token": "token-1"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid terminal session token"


def test_get_terminal_session_requires_token(terminal_env: dict) -> None:
    response = terminal_env["client"].get("/api/terminal/sessions/terminal-1")

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid terminal session token"


def test_close_terminal_session(terminal_env: dict) -> None:
    response = terminal_env["client"].delete(
        "/api/terminal/sessions/terminal-1",
        params={"token": "token-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Terminal session closed",
        "session_id": "terminal-1",
    }
    assert terminal_env["manager"].closed_ids == ["terminal-1"]


def test_terminal_websocket_streams_backlog_and_input(terminal_env: dict) -> None:
    session = terminal_env["session"]

    with terminal_env["client"].websocket_connect(
        "/api/terminal/sessions/terminal-1/stream?token=token-1",
        headers={"origin": "http://localhost:3000"},
    ) as websocket:
        assert websocket.receive_json() == {"type": "status", "status": "running"}
        assert websocket.receive_json() == {
            "type": "output",
            "stream": "stdout",
            "data": "ready\r\n",
        }

        websocket.send_json({"type": "input", "data": "adb devices\n"})
        websocket.send_json({"type": "resize", "cols": 120, "rows": 40})
        session.queue.put_nowait(
            {
                "type": "output",
                "stream": "stdout",
                "data": "List of devices attached\n",
            }
        )

        assert websocket.receive_json() == {
            "type": "output",
            "stream": "stdout",
            "data": "List of devices attached\n",
        }

    assert session.inputs == ["adb devices\n"]
    assert session.resizes == [(120, 40)]
    assert session.unsubscribed is True


def test_terminal_disabled_for_non_local_host_by_default(
    terminal_env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTOGLM_SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("AUTOGLM_ENABLE_WEB_TERMINAL", raising=False)

    response = terminal_env["client"].post("/api/terminal/sessions", json={})

    assert response.status_code == 403
    assert "AUTOGLM_ENABLE_WEB_TERMINAL=1" in response.json()["detail"]
