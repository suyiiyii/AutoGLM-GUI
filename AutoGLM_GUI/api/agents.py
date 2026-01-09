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


@router.post("/api/init", deprecated=True)
def init_agent(request: InitRequest) -> dict:
    """初始化 PhoneAgent（已废弃，多设备支持）。

    ⚠️ 此端点已废弃，将在未来版本移除。

    Agent 现在会在首次使用时自动初始化，无需手动调用此端点。
    如需修改配置，请使用 /api/config 端点或直接修改配置文件 ~/.config/autoglm/config.json。
    配置保存后会自动销毁所有 Agent，确保下次使用时应用新配置。

    配置完全由 ConfigManager 提供（CLI > ENV > FILE > DEFAULT），
    不接受运行时覆盖。
    """
    from AutoGLM_GUI.config_manager import config_manager

    device_id = request.device_id
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")

    # 热重载配置文件（支持运行时手动修改）
    config_manager.load_file_config()
    config_manager.sync_to_env()

    # 获取有效配置（CLI > ENV > FILE > DEFAULT）
    effective_config = config_manager.get_effective_config()

    if not effective_config.base_url:
        raise HTTPException(
            status_code=400,
            detail="base_url is required. Please configure via Settings or start with --base-url",
        )

    # 直接使用有效配置构造 ModelConfig 和 AgentConfig
    model_config = ModelConfig(
        base_url=effective_config.base_url,
        api_key=effective_config.api_key,
        model_name=effective_config.model_name,
        # max_tokens, temperature, top_p, frequency_penalty 使用 ModelConfig 默认值
    )

    agent_config = AgentConfig(
        max_steps=effective_config.default_max_steps,
        device_id=device_id,
        # lang, system_prompt, verbose 使用 AgentConfig 默认值
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

        logger.warning(
            f"/api/init is deprecated. Agent of type '{request.agent_type}' initialized for device {device_id}. "
            f"Consider using auto-initialization instead."
        )
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "device_id": device_id,
        "message": f"Agent initialized for device {device_id} (⚠️ /api/init is deprecated)",
        "agent_type": request.agent_type,
        "deprecated": True,
        "hint": "Agent 会在首次使用时自动初始化，无需手动调用此端点",
    }


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """发送任务给 Agent 并执行。

    Agent 会在首次使用时自动初始化，无需手动调用 /api/init。
    """
    from AutoGLM_GUI.exceptions import AgentInitializationError, DeviceBusyError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    manager = PhoneAgentManager.get_instance()

    # use_agent 默认 auto_initialize=True，会自动初始化 Agent
    try:
        with manager.use_agent(device_id, timeout=None) as agent:
            result = agent.run(request.message)
            steps = agent.step_count
            agent.reset()
            return ChatResponse(result=result, steps=steps, success=True)
    except AgentInitializationError as e:
        # 配置错误或初始化失败
        logger.error(f"Failed to initialize agent for {device_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"初始化失败: {str(e)}. 请检查全局配置 (base_url, api_key, model_name)",
        )
    except DeviceBusyError:
        raise HTTPException(
            status_code=409, detail=f"Device {device_id} is busy. Please wait."
        )
    except Exception as e:
        logger.exception(f"Unexpected error in chat for {device_id}")
        return ChatResponse(result=str(e), steps=0, success=False)


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """发送任务给 Agent 并实时推送执行进度（SSE，多设备支持）。

    Agent 会在首次使用时自动初始化，无需手动调用 /api/init。
    """
    from datetime import datetime

    from AutoGLM_GUI.agents.stream_runner import AgentStepStreamer
    from AutoGLM_GUI.device_manager import DeviceManager
    from AutoGLM_GUI.exceptions import AgentInitializationError, DeviceBusyError
    from AutoGLM_GUI.history_manager import history_manager
    from AutoGLM_GUI.models.history import ConversationRecord, MessageRecord
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    manager = PhoneAgentManager.get_instance()

    def event_generator():
        acquired = False
        start_time = datetime.now()
        final_message = ""
        final_success = False
        final_steps = 0

        # 收集完整对话消息
        messages: list[MessageRecord] = []
        # 添加用户消息
        messages.append(
            MessageRecord(
                role="user",
                content=request.message,
                timestamp=start_time,
            )
        )

        try:
            acquired = manager.acquire_device(
                device_id, timeout=0, raise_on_timeout=True, auto_initialize=True
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

                        # 收集每个 step 的消息
                        if event_type == AgentEventType.STEP.value:
                            messages.append(
                                MessageRecord(
                                    role="assistant",
                                    content="",
                                    timestamp=datetime.now(),
                                    thinking=event_data_dict.get("thinking"),
                                    action=event_data_dict.get("action"),
                                    step=event_data_dict.get("step"),
                                )
                            )

                        if event_type == AgentEventType.DONE.value:
                            final_message = event_data_dict.get("message", "")
                            final_success = event_data_dict.get("success", False)
                            final_steps = event_data_dict.get("steps", 0)

                        event_data = _create_sse_event(event_type, event_data_dict)

                        yield f"event: {event_type}\n"
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            finally:
                if acquired:
                    manager.release_device(device_id)

                device_manager = DeviceManager.get_instance()
                serialno = device_manager.get_serial_by_device_id(device_id)
                if serialno and final_message:
                    end_time = datetime.now()
                    record = ConversationRecord(
                        task_text=request.message,
                        final_message=final_message,
                        success=final_success,
                        steps=final_steps,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=int((end_time - start_time).total_seconds() * 1000),
                        source="chat",
                        error_message=None if final_success else final_message,
                        messages=messages,
                    )
                    history_manager.add_record(serialno, record)

        except AgentInitializationError as e:
            logger.error(f"Failed to initialize agent for {device_id}: {e}")
            error_data = _create_sse_event(
                "error",
                {
                    "message": f"初始化失败: {str(e)}",
                    "hint": "请检查全局配置 (base_url, api_key, model_name)",
                },
            )
            yield "event: error\n"
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
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
        decision_base_url=effective_config.decision_base_url,
        decision_model_name=effective_config.decision_model_name,
        decision_api_key=effective_config.decision_api_key,
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
    """保存配置到文件.

    副作用：保存配置后会自动销毁所有已初始化的 Agent，
    确保下次使用时所有 Agent 都使用新配置。
    """
    from AutoGLM_GUI.config_manager import ConfigModel, config_manager
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

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
            decision_base_url=request.decision_base_url,
            decision_model_name=request.decision_model_name,
            decision_api_key=request.decision_api_key,
            merge_mode=True,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save config")

        # 同步到环境变量
        config_manager.sync_to_env()

        # 副作用：销毁所有已初始化的 Agent，确保下次使用新配置
        manager = PhoneAgentManager.get_instance()
        destroyed_agents = manager.list_agents()  # 获取需要销毁的 agent 列表

        for device_id in destroyed_agents:
            try:
                manager.destroy_agent(device_id)
                logger.info(f"Destroyed agent for {device_id} after config change")
            except Exception as e:
                logger.warning(f"Failed to destroy agent for {device_id}: {e}")

        # 检测冲突并返回警告
        conflicts = config_manager.detect_conflicts()

        response_message = f"Configuration saved to {config_manager.get_config_path()}"
        if destroyed_agents:
            response_message += (
                f". Destroyed {len(destroyed_agents)} agent(s) to apply new config."
            )

        if conflicts:
            warnings = [
                f"{c.field}: file value overridden by {c.override_source.value}"
                for c in conflicts
            ]
            return {
                "success": True,
                "message": response_message,
                "warnings": warnings,
                "destroyed_agents": len(destroyed_agents),
            }

        return {
            "success": True,
            "message": response_message,
            "destroyed_agents": len(destroyed_agents),
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


# ✅ 已删除 /api/agents/reinit-all 端点
# 原因：配置保存时自动销毁所有 Agent（副作用），无需单独的 reinit 端点
# 见 /api/config POST 端点的实现
