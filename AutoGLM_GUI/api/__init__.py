"""FastAPI application factory and route registration."""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from AutoGLM_GUI.adb_plus.qr_pair import qr_pairing_manager
from AutoGLM_GUI.version import APP_VERSION

from . import (
    agents,
    control,
    devices,
    health,
    history,
    layered_agent,
    mcp,
    media,
    metrics,
    scheduled_tasks,
    version,
    workflows,
)


def _get_cors_origins() -> list[str]:
    cors_origins_str = os.getenv("AUTOGLM_CORS_ORIGINS", "http://localhost:3000")
    if cors_origins_str == "*":
        return ["*"]
    return [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]


def _get_static_dir() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled_static = Path(meipass) / "AutoGLM_GUI" / "static"
        if bundled_static.exists():
            return bundled_static

    # Priority 2: Check filesystem directly (for Docker deployments)
    # This handles the case where static files are copied to the package directory
    # but not included in the Python package itself (e.g., Docker builds)
    try:
        from AutoGLM_GUI import __file__ as package_file

        package_dir = Path(package_file).parent
        filesystem_static = package_dir / "static"
        if filesystem_static.exists() and filesystem_static.is_dir():
            return filesystem_static
    except (ImportError, AttributeError):
        pass

    # Priority 3: importlib.resources (for installed package)
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

    # Create MCP ASGI app
    mcp_app = mcp.get_mcp_asgi_app()

    # Define combined lifespan
    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        """Combine app startup logic with MCP lifespan."""
        # App startup
        asyncio.create_task(qr_pairing_manager.cleanup_expired_sessions())

        from AutoGLM_GUI.device_manager import DeviceManager
        from AutoGLM_GUI.scheduler_manager import scheduler_manager

        device_manager = DeviceManager.get_instance()
        device_manager.start_polling()

        # Start scheduled task scheduler
        scheduler_manager.start()

        # Run MCP lifespan
        async with mcp_app.lifespan(app):
            yield

        # App shutdown
        scheduler_manager.shutdown()

    # Create FastAPI app with combined lifespan
    app = FastAPI(
        title="AutoGLM-GUI API", version=APP_VERSION, lifespan=combined_lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(agents.router)
    app.include_router(health.router)
    app.include_router(history.router)
    app.include_router(layered_agent.router)
    app.include_router(devices.router)
    app.include_router(control.router)
    app.include_router(media.router)
    app.include_router(metrics.router)
    app.include_router(scheduled_tasks.router)
    app.include_router(version.router)
    app.include_router(workflows.router)

    # Mount static files BEFORE MCP to ensure they have priority
    # This is critical: FastAPI processes mounts in order, so static files
    # must be mounted before the catch-all MCP mount
    static_dir = _get_static_dir()
    if static_dir is not None and static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            # Vite builds assets with content hashes, so we can cache them long-term
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        # Define SPA serving function
        async def serve_spa(full_path: str) -> FileResponse:
            file_path = static_dir / full_path
            if file_path.is_file():
                # Explicitly set media_type for common file types to avoid MIME detection issues
                # This is critical for PyInstaller environments where mimetypes module may fail
                media_type = None
                suffix = file_path.suffix.lower()
                if suffix == ".js":
                    media_type = "application/javascript"
                elif suffix == ".css":
                    media_type = "text/css"
                elif suffix == ".json":
                    media_type = "application/json"
                elif suffix in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"):
                    # Let FileResponse auto-detect image types (usually works)
                    media_type = None

                return FileResponse(
                    file_path,
                    media_type=media_type,
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
            return FileResponse(
                static_dir / "index.html",
                media_type="text/html",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        # Add catch-all route for SPA (handles all non-API routes)
        app.add_api_route(
            "/{full_path:path}", serve_spa, methods=["GET"], include_in_schema=False
        )

    # Mount MCP server at root (mcp_app already has /mcp path prefix)
    # This must be AFTER static files to avoid intercepting them
    app.mount("/", mcp_app)

    return app


app = create_app()
