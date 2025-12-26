"""FastAPI application factory and route registration."""

import asyncio
import sys
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from AutoGLM_GUI.version import APP_VERSION
from AutoGLM_GUI.adb_plus.qr_pair import qr_pairing_manager

from . import agents, control, devices, media, version


def _get_static_dir() -> Path | None:
    """Locate packaged static assets."""
    # Priority 1: PyInstaller bundled path (for packaged executable)
    if getattr(sys, "_MEIPASS", None):
        bundled_static = Path(sys._MEIPASS) / "AutoGLM_GUI" / "static"
        if bundled_static.exists():
            return bundled_static

    # Priority 2: importlib.resources (for installed package)
    try:
        static_dir = files("AutoGLM_GUI").joinpath("static")
        if hasattr(static_dir, "_path"):
            path = Path(str(static_dir))
            if path.exists():
                return path
        path = Path(str(static_dir))
        if path.exists():
            return path
    except (TypeError, FileNotFoundError):
        pass

    return None


def create_app() -> FastAPI:
    """Build the FastAPI app with routers and static assets."""
    app = FastAPI(title="AutoGLM-GUI API", version=APP_VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(agents.router)
    app.include_router(devices.router)
    app.include_router(control.router)
    app.include_router(media.router)
    app.include_router(version.router)

    @app.on_event("startup")
    async def startup_event():
        """Initialize background tasks on server startup."""
        # Start QR pairing session cleanup task
        asyncio.create_task(qr_pairing_manager.cleanup_expired_sessions())

    static_dir = _get_static_dir()
    if static_dir is not None and static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> FileResponse:
            file_path = static_dir / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
