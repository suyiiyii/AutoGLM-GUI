"""Agent lifecycle and chat routes."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from AutoGLM_GUI.agents.events import AgentEventType
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.schemas import (
    AbortRequest,
    APIAgentConfig,
    APIModelConfig,
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    ConfigSaveRequest,
    InitRequest,
    ResetRequest,
    StatusResponse,
)
from AutoGLM_GUI.state import (
    non_blocking_takeover,
)
from AutoGLM_GUI.version import APP_VERSION

router = APIRouter()


def _setup_adb_keyboard(device_id: str) -> None:
    """检查并自动安装 ADB Keyboard。

    Args:
        device_id: 设备 ID
    """
    from AutoGLM_GUI.adb_plus import ADBKeyboardInstaller

    logger.info(f"Checking ADB Keyboard for device {device_id}...")
    installer = ADBKeyboardInstaller(device_id=device_id)
    status = installer.get_status()

    if not (status["installed"] and status["enabled"]):
        logger.info(f"Setting up ADB Keyboard for device {device_id}...")
        success, message = installer.auto_setup()
        if success:
            logger.info(f"✓ Device {device_id}: {message}")
        else:
            logger.warning(f"✗ Device {device_id}: {message}")
    else:
        logger.info(f"✓ Device {device_id}: ADB Keyboard ready")


SSEPayload = dict[str, str | int | bool | None | dict]


def _create_sse_event(
    event_type: str, data: SSEPayload, role: str = "assistant"
) -> SSEPayload:
    """Create an SSE event with standardized fields including role."""
    event_data = {"type": event_type, "role": role, **data}
    return event_data


@router.post("/api/init")
def init_agent(request: InitRequest) -> dict:
    """初始化 PhoneAgent（多设备支持）。"""
    from AutoGLM_GUI.config_manager import config_manager

    req_model_config = request.model or APIModelConfig()
    req_agent_config = request.agent or APIAgentConfig()

    device_id = req_agent_config.device_id
    if not device_id:
        raise HTTPException(
            status_code=400, detail="device_id is required in agent_config"
        )

    # 热重载配置文件（支持运行时手动修改）
    config_manager.load_file_config()
    config_manager.sync_to_env()

    # 获取有效配置（已合并 CLI > ENV > FILE > DEFAULT）
    effective_config = config_manager.get_effective_config()

    # 优先级：请求参数 > 有效配置
    base_url = req_model_config.base_url or effective_config.base_url
    api_key = req_model_config.api_key or effective_config.api_key
    model_name = req_model_config.model_name or effective_config.model_name

    # 获取配置的默认最大步数
    max_steps = effective_config.default_max_steps

    if not base_url:
        raise HTTPException(
            status_code=400,
            detail="base_url is required. Please configure via Settings or start with --base-url",
        )

    model_config = ModelConfig(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        max_tokens=req_model_config.max_tokens,
        temperature=req_model_config.temperature,
        top_p=req_model_config.top_p,
        frequency_penalty=req_model_config.frequency_penalty,
    )

    agent_config = AgentConfig(
        max_steps=max_steps,
        device_id=device_id,
        lang=req_agent_config.lang,
        system_prompt=req_agent_config.system_prompt,
        verbose=req_agent_config.verbose,
    )

    # Initialize agent (includes ADB Keyboard setup)
    try:
        # Setup ADB Keyboard (common for all agents)
        _setup_adb_keyboard(device_id)

        # Use agent factory to create agent
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

        manager = PhoneAgentManager.get_instance()

        # Initialize agent using factory pattern
        from typing import cast

        from AutoGLM_GUI.types import AgentSpecificConfig

        agent_config_params = cast(
            AgentSpecificConfig, request.agent_config_params or {}
        )
        manager.initialize_agent_with_factory(
            device_id=device_id,
            agent_type=request.agent_type,
            model_config=model_config,
            agent_config=agent_config,
            agent_specific_config=agent_config_params,
            takeover_callback=non_blocking_takeover,
            force=request.force,
        )

        logger.info(
            f"Agent of type '{request.agent_type}' initialized for device {device_id}"
        )
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "device_id": device_id,
        "message": f"Agent initialized for device {device_id}",
        "agent_type": request.agent_type,
    }


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """发送任务给 Agent 并执行。"""
    from AutoGLM_GUI.exceptions import DeviceBusyError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    manager = PhoneAgentManager.get_instance()

    # Check if agent is initialized
    if not manager.is_initialized(device_id):
        raise HTTPException(
            status_code=400, detail="Agent not initialized. Call /api/init first."
        )

    # Use context manager for automatic lock management
    try:
        with manager.use_agent(device_id, timeout=None) as agent:
            result = agent.run(request.message)
            steps = agent.step_count
            agent.reset()
            return ChatResponse(result=result, steps=steps, success=True)
    except DeviceBusyError:
        raise HTTPException(
            status_code=409, detail=f"Device {device_id} is busy. Please wait."
        )
    except Exception as e:
        return ChatResponse(result=str(e), steps=0, success=False)


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """发送任务给 Agent 并实时推送执行进度（SSE，多设备支持）。"""
    from AutoGLM_GUI.agents.stream_runner import AgentStepStreamer
    from AutoGLM_GUI.exceptions import DeviceBusyError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    manager = PhoneAgentManager.get_instance()

    # 验证 agent 已初始化
    if not manager.is_initialized(device_id):
        raise HTTPException(
            status_code=400,
            detail=f"Device {device_id} not initialized. Call /api/init first.",
        )

    def event_generator():
        try:
            acquired = manager.acquire_device(
                device_id, timeout=0, raise_on_timeout=True
            )

            try:
                agent = manager.get_agent(device_id)
                streamer = AgentStepStreamer(agent=agent, task=request.message)

                with streamer.stream_context() as abort_fn:
                    manager.register_abort_handler(device_id, abort_fn)

                    for event in streamer:
                        event_type = event["type"]
                        event_data_dict = event["data"]

                        if (
                            event_type == AgentEventType.STEP.value
                            and event_data_dict.get("step") == -1
                        ):
                            continue

                        event_data = _create_sse_event(event_type, event_data_dict)

                        yield f"event: {event_type}\n"
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            finally:
                if acquired:
                    manager.release_device(device_id)

        except DeviceBusyError:
            error_data = _create_sse_event("error", {"message": "Device is busy"})
            yield "event: error\n"
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"Error in streaming chat for {device_id}")
            error_data = _create_sse_event("error", {"message": str(e)})
            yield "event: error\n"
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        finally:
            manager.unregister_abort_handler(device_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/status", response_model=StatusResponse)
def get_status(device_id: str | None = None) -> StatusResponse:
    """获取 Agent 状态和版本信息（多设备支持）。"""
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    manager = PhoneAgentManager.get_instance()

    if device_id is None:
        return StatusResponse(
            version=APP_VERSION,
            initialized=len(manager.list_agents()) > 0,
            step_count=0,
        )

    if not manager.is_initialized(device_id):
        return StatusResponse(
            version=APP_VERSION,
            initialized=False,
            step_count=0,
        )

    agent = manager.get_agent(device_id)
    return StatusResponse(
        version=APP_VERSION,
        initialized=True,
        step_count=agent.step_count,
    )


@router.post("/api/reset")
def reset_agent(request: ResetRequest) -> dict:
    """重置 Agent 状态（多设备支持）。"""
    from AutoGLM_GUI.exceptions import AgentNotInitializedError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    manager = PhoneAgentManager.get_instance()

    try:
        manager.reset_agent(device_id)
        return {
            "success": True,
            "device_id": device_id,
            "message": f"Agent reset for device {device_id}",
        }
    except AgentNotInitializedError:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")


@router.post("/api/chat/abort")
def abort_chat(request: AbortRequest) -> dict:
    """中断正在进行的对话流。"""
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    manager = PhoneAgentManager.get_instance()

    success = manager.abort_streaming_chat(device_id)

    return {
        "success": success,
        "message": "Abort requested" if success else "No active chat found",
    }


@router.get("/api/config", response_model=ConfigResponse)
def get_config_endpoint() -> ConfigResponse:
    """获取当前有效配置."""
    from AutoGLM_GUI.config_manager import config_manager

    # 热重载：检查文件是否被外部修改
    config_manager.load_file_config()

    # 获取有效配置和来源
    effective_config = config_manager.get_effective_config()
    source = config_manager.get_config_source()

    # 检测冲突
    conflicts = config_manager.detect_conflicts()

    return ConfigResponse(
        base_url=effective_config.base_url,
        model_name=effective_config.model_name,
        api_key=effective_config.api_key if effective_config.api_key != "EMPTY" else "",
        source=source.value,
        agent_type=effective_config.agent_type,
        agent_config_params=effective_config.agent_config_params,
        default_max_steps=effective_config.default_max_steps,
        conflicts=[
            {
                "field": c.field,
                "file_value": c.file_value,
                "override_value": c.override_value,
                "override_source": c.override_source.value,
            }
            for c in conflicts
        ]
        if conflicts
        else None,
    )


@router.post("/api/config")
def save_config_endpoint(request: ConfigSaveRequest) -> dict:
    """保存配置到文件."""
    from AutoGLM_GUI.config_manager import ConfigModel, config_manager

    try:
        # Validate incoming configuration
        ConfigModel(
            base_url=request.base_url,
            model_name=request.model_name,
            api_key=request.api_key or "EMPTY",
        )

        # 保存配置（合并模式，不丢失字段）
        success = config_manager.save_file_config(
            base_url=request.base_url,
            model_name=request.model_name,
            api_key=request.api_key,
            agent_type=request.agent_type,
            agent_config_params=request.agent_config_params,
            default_max_steps=request.default_max_steps,
            merge_mode=True,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save config")

        # 同步到环境变量
        config_manager.sync_to_env()

        # 检测冲突并返回警告
        conflicts = config_manager.detect_conflicts()

        if conflicts:
            warnings = [
                f"{c.field}: file value overridden by {c.override_source.value}"
                for c in conflicts
            ]
            return {
                "success": True,
                "message": f"Configuration saved to {config_manager.get_config_path()}",
                "warnings": warnings,
            }

        return {
            "success": True,
            "message": f"Configuration saved to {config_manager.get_config_path()}",
        }

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/config")
def delete_config_endpoint() -> dict:
    """删除配置文件."""
    from AutoGLM_GUI.config_manager import config_manager

    try:
        success = config_manager.delete_file_config()

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete config")

        return {"success": True, "message": "Configuration deleted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
