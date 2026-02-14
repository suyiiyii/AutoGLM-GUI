"""Regression tests for frontend static asset MIME handling."""

from __future__ import annotations

from pathlib import Path

import starlette.responses as starlette_responses
import pytest
from fastapi.testclient import TestClient

from AutoGLM_GUI import api as api_module

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


def test_assets_js_mime_type_is_javascript_when_guess_type_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)

    (static_dir / "index.html").write_text(
        "<!doctype html><html></html>", encoding="utf-8"
    )
    (assets_dir / "index-test.js").write_text("console.log('ok');", encoding="utf-8")

    # Simulate environments where system mime db is missing and FileResponse falls back to text/plain.
    monkeypatch.setattr(
        starlette_responses, "guess_type", lambda *_args, **_kwargs: (None, None)
    )
    monkeypatch.setattr(api_module, "_get_static_dir", lambda: static_dir)

    app = api_module.create_app()
    client = TestClient(app)

    response = client.get("/assets/index-test.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_assets_css_mime_type_when_guess_type_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)

    (static_dir / "index.html").write_text(
        "<!doctype html><html></html>", encoding="utf-8"
    )
    (assets_dir / "style.css").write_text("body { margin: 0; }", encoding="utf-8")

    monkeypatch.setattr(
        starlette_responses, "guess_type", lambda *_args, **_kwargs: (None, None)
    )
    monkeypatch.setattr(api_module, "_get_static_dir", lambda: static_dir)

    app = api_module.create_app()
    client = TestClient(app)

    response = client.get("/assets/style.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_spa_favicon_mime_type_when_guess_type_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)

    (static_dir / "index.html").write_text(
        "<!doctype html><html></html>", encoding="utf-8"
    )
    (static_dir / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")

    monkeypatch.setattr(
        starlette_responses, "guess_type", lambda *_args, **_kwargs: (None, None)
    )
    monkeypatch.setattr(api_module, "_get_static_dir", lambda: static_dir)

    app = api_module.create_app()
    client = TestClient(app)

    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert "image/x-icon" in response.headers["content-type"]
