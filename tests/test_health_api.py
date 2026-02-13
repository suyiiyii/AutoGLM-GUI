"""Contract tests for health endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from AutoGLM_GUI.api.health import router as health_router
from AutoGLM_GUI.version import APP_VERSION

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


def test_health_check_returns_expected_payload() -> None:
    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "version": APP_VERSION,
    }
