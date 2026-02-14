"""Contract tests for layered agent session control endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.layered_agent as layered_agent_api

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeRun:
    def __init__(self) -> None:
        self.cancel_calls: list[str] = []

    def cancel(self, mode: str) -> None:
        self.cancel_calls.append(mode)


@pytest.fixture
def layered_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    fake_runs: dict[str, FakeRun] = {}
    fake_sessions: dict[str, object] = {}

    monkeypatch.setattr(layered_agent_api, "_active_runs", fake_runs)
    monkeypatch.setattr(layered_agent_api, "_sessions", fake_sessions)

    app = FastAPI()
    app.include_router(layered_agent_api.router)

    return {
        "client": TestClient(app),
        "runs": fake_runs,
        "sessions": fake_sessions,
    }


def test_abort_session_success(layered_env: dict[str, Any]) -> None:
    run = FakeRun()
    layered_env["runs"]["session-1"] = run

    response = layered_env["client"].post(
        "/api/layered-agent/abort",
        json={"session_id": "session-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Session session-1 abort signal sent",
    }
    assert run.cancel_calls == ["immediate"]


def test_abort_session_not_found(layered_env: dict[str, Any]) -> None:
    response = layered_env["client"].post(
        "/api/layered-agent/abort",
        json={"session_id": "missing-session"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "message": "No active run found for session missing-session",
    }


def test_reset_session_clears_existing_session(layered_env: dict[str, Any]) -> None:
    layered_env["sessions"]["session-2"] = object()

    response = layered_env["client"].post(
        "/api/layered-agent/reset",
        json={"session_id": "session-2"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Session session-2 cleared",
    }


def test_reset_session_is_idempotent(layered_env: dict[str, Any]) -> None:
    response = layered_env["client"].post(
        "/api/layered-agent/reset",
        json={"session_id": "unknown-session"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Session unknown-session not found (already empty)",
    }
