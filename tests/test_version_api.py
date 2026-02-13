"""Contract tests for version check API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.version as version_api

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


@pytest.fixture(autouse=True)
def reset_version_cache() -> None:
    version_api._version_cache["data"] = None
    version_api._version_cache["timestamp"] = 0
    version_api._version_cache["ttl"] = 3600


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(version_api.router)
    return TestClient(app)


def test_parse_version_handles_common_formats() -> None:
    assert version_api.parse_version("1.2.3") == (1, 2, 3)
    assert version_api.parse_version("v2.0.1") == (2, 0, 1)
    assert version_api.parse_version("3.4.5-beta") == (3, 4, 5)
    assert version_api.parse_version("dev") is None


def test_compare_versions() -> None:
    assert version_api.compare_versions("1.0.0", "1.0.1") is True
    assert version_api.compare_versions("1.0.0", "1.0.0") is False
    assert version_api.compare_versions("dev", "9.9.9") is False


def test_version_endpoint_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        version_api,
        "fetch_latest_release",
        lambda: {
            "tag_name": "v99.0.0",
            "html_url": "https://example.com/release",
            "published_at": "2026-02-01T00:00:00Z",
        },
    )

    response = client.get("/api/version/latest")

    assert response.status_code == 200
    data = response.json()
    assert data["latest_version"] == "99.0.0"
    assert data["release_url"] == "https://example.com/release"
    assert data["published_at"] == "2026-02-01T00:00:00Z"
    assert data["error"] is None


def test_version_endpoint_failure_without_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(version_api, "fetch_latest_release", lambda: None)

    response = client.get("/api/version/latest")

    assert response.status_code == 200
    data = response.json()
    assert data["has_update"] is False
    assert data["latest_version"] is None
    assert data["error"] == "Failed to fetch latest version from GitHub"


def test_version_endpoint_uses_cache(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def fake_fetch_latest_release():
        calls["count"] += 1
        return {
            "tag_name": "v1.0.0",
            "html_url": "https://example.com/r1",
            "published_at": "2026-01-01T00:00:00Z",
        }

    fake_time = {"now": 1000.0}

    monkeypatch.setattr(version_api, "fetch_latest_release", fake_fetch_latest_release)
    monkeypatch.setattr(version_api.time, "time", lambda: fake_time["now"])

    first = client.get("/api/version/latest")
    assert first.status_code == 200

    fake_time["now"] = 1005.0  # still within TTL
    second = client.get("/api/version/latest")
    assert second.status_code == 200

    assert calls["count"] == 1
    assert first.json() == second.json()


def test_version_endpoint_falls_back_to_stale_cache_on_fetch_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"ok": True}

    def maybe_fetch_latest_release():
        if state["ok"]:
            return {
                "tag_name": "v1.1.0",
                "html_url": "https://example.com/r2",
                "published_at": "2026-01-02T00:00:00Z",
            }
        return None

    fake_time = {"now": 2000.0}

    monkeypatch.setattr(version_api, "fetch_latest_release", maybe_fetch_latest_release)
    monkeypatch.setattr(version_api.time, "time", lambda: fake_time["now"])

    first = client.get("/api/version/latest")
    assert first.status_code == 200
    assert first.json()["latest_version"] == "1.1.0"

    state["ok"] = False
    fake_time["now"] = 2000.0 + version_api._version_cache["ttl"] + 1

    second = client.get("/api/version/latest")
    assert second.status_code == 200
    assert second.json() == first.json()
