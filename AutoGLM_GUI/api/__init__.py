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
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.version import APP_VERSION

from . import (
    agents,
    control,
    devices,
    dual_model,
    health,
    layered_agent,
    mcp,
    media,
    metrics,
    scheduled_tasks,
    version,
    workflows,
)


def _inject_unified_device_protocol() -> None:
    """Inject unified device protocol supporting both ADB and Remote devices."""
    from AutoGLM_GUI.device_adapter import inject_device_protocol

    if remote_base_url := os.getenv("REMOTE_DEVICE_BASE_URL"):
        from AutoGLM_GUI.devices.remote_device import RemoteDevice

        def get_remote_device(device_id: str | None):
            return RemoteDevice(device_id or "mock_device_001", remote_base_url)

        inject_device_protocol(get_remote_device)
        logger.info(f"Remote device mode enabled: connecting to {remote_base_url}")
        return

    from AutoGLM_GUI.device_manager import DeviceManager
    from AutoGLM_GUI.device_protocol import DeviceProtocol
    from AutoGLM_GUI.devices.adb_device import ADBDevice

    device_manager = DeviceManager.get_instance()

    def get_device_by_id(device_id: str | None) -> DeviceProtocol:
        if not device_id:
            raise ValueError("device_id is required")

        managed = device_manager.get_device_by_device_id(device_id)
        if not managed:
            raise ValueError(f"Device {device_id} not found")

        if managed.connection_type.value == "remote":
            remote_device = device_manager.get_remote_device_instance(managed.serial)
            if not remote_device:
                raise ValueError(f"Remote device instance not found: {managed.serial}")
            return remote_device  # type: ignore
        else:
            return ADBDevice(managed.primary_device_id)

    inject_device_protocol(get_device_by_id)
    logger.info("Unified device protocol injected (ADB + Remote)")


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

    _inject_unified_device_protocol()

    # Create MCP ASGI app
    mcp_app = mcp.get_mcp_asgi_app()

    # Define combined lifespan
    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        """Combine app startup logic with MCP lifespan."""
        # App startup
        asyncio.create_task(qr_pairing_manager.cleanup_expired_sessions())

        from AutoGLM_GUI.device_manager import DeviceManager

        device_manager = DeviceManager.get_instance()
        device_manager.start_polling()

        # Start scheduled task scheduler
        from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

        scheduled_task_manager.start_scheduler()

        # Set task executor
        def task_executor(
            task_uuid: str, device_id: str, message: str, execution_mode: str
        ) -> str:
            """Execute scheduled task with different execution modes.
            
            Returns:
                str: Detailed execution result
            """
            from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
            from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

            logger.info(
                f"Executing scheduled task {task_uuid} with mode: {execution_mode}"
            )

            if execution_mode == "dual_model":
                # 双模型协作模式
                return _execute_dual_model_task(task_uuid, device_id, message)
            elif execution_mode == "layered_agent":
                # 分层代理模式
                return _execute_layered_agent_task(task_uuid, device_id, message)
            else:
                # 经典模式（默认）
                manager = PhoneAgentManager.get_instance()
                if not manager.is_initialized(device_id):
                    raise RuntimeError(f"Device {device_id} not initialized")

                with manager.use_agent(device_id, timeout=None) as agent:
                    result = agent.run(message)
                    steps = agent.step_count
                    agent.reset()
                    return f"任务完成 (经典模式)\n执行步数: {steps}\n结果: {result}"

        def _execute_dual_model_task(
            task_uuid: str, device_id: str, message: str
        ) -> str:
            """Execute task using dual model mode.
            
            Returns:
                str: Detailed execution result
            """
            from AutoGLM_GUI.config import ModelConfig
            from AutoGLM_GUI.config_manager import config_manager
            from AutoGLM_GUI.dual_model import (
                DecisionModelConfig,
                DualModelAgent,
                DualModelEventType,
            )
            from AutoGLM_GUI.dual_model.protocols import ThinkingMode
            from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
            from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

            # 检查设备是否已初始化
            manager = PhoneAgentManager.get_instance()
            if not manager.is_initialized(device_id):
                raise RuntimeError(f"Device {device_id} not initialized")

            # 获取任务配置
            task = scheduled_task_manager.get_task(task_uuid)
            thinking_mode_str = task.get("thinking_mode", "deep") if task else "deep"
            thinking_mode_map = {
                "fast": ThinkingMode.FAST,
                "deep": ThinkingMode.DEEP,
                "turbo": ThinkingMode.TURBO,
            }
            thinking_mode = thinking_mode_map.get(thinking_mode_str, ThinkingMode.DEEP)

            # 获取配置
            effective_config = config_manager.get_effective_config()

            if not effective_config.dual_model_enabled:
                raise RuntimeError("Dual model not enabled in config")

            # 创建决策模型配置
            decision_config = DecisionModelConfig(
                base_url=effective_config.decision_base_url,
                api_key=effective_config.decision_api_key,
                model_name=effective_config.decision_model_name,
                thinking_mode=thinking_mode,
            )

            # 创建视觉模型配置
            vision_config = ModelConfig(
                base_url=effective_config.base_url,
                api_key=effective_config.api_key,
                model_name=effective_config.model_name,
            )

            # 创建双模型Agent
            agent = DualModelAgent(
                decision_config=decision_config,
                vision_config=vision_config,
                device_id=device_id,
                max_steps=effective_config.default_max_steps,
                thinking_mode=thinking_mode,
            )

            try:
                result = agent.run(message)
                steps = getattr(agent, "step_count", 0)
                success = result.get("success", False) if isinstance(result, dict) else True
                result_msg = result.get("message", str(result)) if isinstance(result, dict) else str(result)
                
                logger.info(f"Dual model task completed: {result}")
                return f"任务完成 (双模型协作 - {thinking_mode.value}模式)\n执行步数: {steps}\n成功: {'是' if success else '否'}\n结果: {result_msg}"
            finally:
                agent.reset()

        def _execute_layered_agent_task(
            task_uuid: str, device_id: str, message: str
        ) -> str:
            """Execute task using layered agent mode.
            
            Returns:
                str: Detailed execution result
            """
            import asyncio

            from agents import Runner
            from AutoGLM_GUI.api.layered_agent import (
                _ensure_agent,
                _get_or_create_session,
            )
            from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

            # 检查设备是否已初始化
            manager = PhoneAgentManager.get_instance()
            if not manager.is_initialized(device_id):
                raise RuntimeError(f"Device {device_id} not initialized")

            # 使用完整的 layered agent runner
            agent = _ensure_agent()
            session_id = f"scheduled_task_{task_uuid}"
            session = _get_or_create_session(session_id)

            # 在新的事件循环中运行异步任务
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    Runner.run(
                        agent,
                        message,
                        max_turns=50,
                        session=session,
                    )
                )
                final_output = result.final_output if hasattr(result, "final_output") else str(result)
                logger.info(f"Layered agent task completed: {final_output}")
                return f"任务完成 (分层代理模式)\n结果: {final_output}"
            finally:
                loop.close()

        scheduled_task_manager.set_task_executor(task_executor)

        # Run MCP lifespan
        async with mcp_app.lifespan(app):
            yield

        # App shutdown
        scheduled_task_manager.stop_scheduler()

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
    app.include_router(layered_agent.router)
    app.include_router(devices.router)
    app.include_router(control.router)
    app.include_router(media.router)
    app.include_router(metrics.router)
    app.include_router(version.router)
    app.include_router(workflows.router)
    app.include_router(dual_model.router)
    app.include_router(scheduled_tasks.router)

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
                return FileResponse(
                    file_path,
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
            return FileResponse(
                static_dir / "index.html",
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
