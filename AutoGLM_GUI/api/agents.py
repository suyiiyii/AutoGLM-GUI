"""Agent lifecycle and chat routes."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from AutoGLM_GUI.config import config
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.schemas import (
    APIAgentConfig,
    APIModelConfig,
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    ConfigSaveRequest,
    InitRequest,
    InterruptRequest,
    InterruptResponse,
    ResetRequest,
    StatusResponse,
)
from AutoGLM_GUI.state import (
    agent_configs,
    agents,
    non_blocking_takeover,
)
from AutoGLM_GUI.version import APP_VERSION
from AutoGLM_GUI.agent_wrapper import InterruptiblePhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

router = APIRouter()


@router.post("/api/init")
def init_agent(request: InitRequest) -> dict:
    """初始化 PhoneAgent（多设备支持）。"""
    from AutoGLM_GUI.adb_plus import ADBKeyboardInstaller
    from AutoGLM_GUI.config_manager import config_manager
    from AutoGLM_GUI.logger import logger

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
    config.refresh_from_env()

    # 检查并自动安装 ADB Keyboard
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

    base_url = req_model_config.base_url or config.base_url
    api_key = req_model_config.api_key or config.api_key
    model_name = req_model_config.model_name or config.model_name

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
        max_steps=req_agent_config.max_steps,
        device_id=device_id,
        lang=req_agent_config.lang,
        system_prompt=req_agent_config.system_prompt,
        verbose=req_agent_config.verbose,
    )

    agents[device_id] = InterruptiblePhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
        takeover_callback=non_blocking_takeover,
    )

    agent_configs[device_id] = (model_config, agent_config)

    return {
        "success": True,
        "device_id": device_id,
        "message": f"Agent initialized for device {device_id}",
    }


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """发送任务给 Agent 并执行。"""
    from AutoGLM_GUI.exceptions import TaskInterruptedError
    
    device_id = request.device_id
    if device_id not in agents:
        raise HTTPException(
            status_code=400, detail="Agent not initialized. Call /api/init first."
        )

    agent = agents[device_id]

    try:
        result = agent.run(request.message)
        steps = agent.step_count
        agent.reset()

        return ChatResponse(result=result, steps=steps, success=True)
    except TaskInterruptedError:
        # Handle user/task interruption explicitly for consistency with /api/chat/stream
        steps = agent.step_count
        agent.reset()
        return ChatResponse(
            result="Task interrupted",
            steps=steps,
            success=False,
        )
    except Exception as e:
        agent.reset()
        return ChatResponse(result=str(e), steps=0, success=False)


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """发送任务给 Agent 并实时推送执行进度（SSE，多设备支持）。"""
    device_id = request.device_id

    if device_id not in agents:
        raise HTTPException(
            status_code=400,
            detail=f"Device {device_id} not initialized. Call /api/init first.",
        )

    agent = agents[device_id]

    def event_generator():
        """SSE 事件生成器"""
        from AutoGLM_GUI.exceptions import TaskInterruptedError

        try:
            step_result = agent.step(request.message)
            while True:
                # 检查是否已被打断
                if isinstance(agent, InterruptiblePhoneAgent) and agent.interrupted:
                    logger.info(
                        f"Agent for device {device_id} was interrupted, stopping stream."
                    )
                    done_data = {
                        "type": "done",
                        "message": "Task Interrupted",
                        "steps": agent.step_count,
                        "success": False,
                    }
                    yield "event: done\n"
                    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                    break

                event_data = {
                    "type": "step",
                    "step": agent.step_count,
                    "thinking": step_result.thinking,
                    "action": step_result.action,
                    "success": step_result.success,
                    "finished": step_result.finished,
                }

                yield "event: step\n"
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                if step_result.finished:
                    done_data = {
                        "type": "done",
                        "message": step_result.message,
                        "steps": agent.step_count,
                        "success": step_result.success,
                    }
                    yield "event: done\n"
                    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                    break

                if agent.step_count >= agent.agent_config.max_steps:
                    done_data = {
                        "type": "done",
                        "message": "Max steps reached",
                        "steps": agent.step_count,
                        "success": step_result.success,
                    }
                    yield "event: done\n"
                    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                    break

                step_result = agent.step()

            agent.reset()

        except TaskInterruptedError:
            logger.info(f"Task on device {device_id} was interrupted during execution.")
            done_data = {
                "type": "done",
                "message": "Task Interrupted",
                "steps": agent.step_count,
                "success": False,
            }
            yield "event: done\n"
            yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
            agent.reset()
        except Exception as e:
            logger.exception(f"Error in chat_stream: {e}")
            error_data = {
                "type": "error",
                "message": str(e),
            }
            yield "event: error\n"
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/interrupt", response_model=InterruptResponse)
def interrupt_agent(request: InterruptRequest) -> InterruptResponse:
    """打断当前正在执行的任务（多设备支持）。"""
    device_id = request.device_id
    logger.info(f"Received interrupt request for device {device_id}")

    if device_id not in agents:
        logger.warning(f"Interrupt failed: Device {device_id} not initialized.")
        raise HTTPException(
            status_code=404, detail=f"Device {device_id} not initialized."
        )

    agent = agents[device_id]
    if isinstance(agent, InterruptiblePhoneAgent):
        agent.interrupt()
        logger.info(
            f"Successfully sent interrupt signal to agent for device {device_id}"
        )
        return InterruptResponse(
            success=True,
            message=f"Interruption signal sent to device {device_id}",
            device_id=device_id,
        )
    else:
        logger.error(
            f"Interrupt failed: Agent for device {device_id} does not support interruption"
        )
        return InterruptResponse(
            success=False,
            message=f"Agent for device {device_id} does not support interruption",
            device_id=device_id,
        )


@router.get("/api/status", response_model=StatusResponse)
def get_status(device_id: str | None = None) -> StatusResponse:
    """获取 Agent 状态和版本信息（多设备支持）。"""
    if device_id is None:
        return StatusResponse(
            version=APP_VERSION,
            initialized=len(agents) > 0,
            step_count=0,
        )

    if device_id not in agents:
        return StatusResponse(
            version=APP_VERSION,
            initialized=False,
            step_count=0,
        )

    agent = agents[device_id]
    return StatusResponse(
        version=APP_VERSION,
        initialized=True,
        step_count=agent.step_count,
    )


@router.post("/api/reset")
def reset_agent(request: ResetRequest) -> dict:
    """重置 Agent 状态（多设备支持）。"""
    device_id = request.device_id

    if device_id not in agents:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    agent = agents[device_id]
    agent.reset()

    if device_id in agent_configs:
        model_config, agent_config = agent_configs[device_id]
        agents[device_id] = InterruptiblePhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
            takeover_callback=non_blocking_takeover,
        )

    return {
        "success": True,
        "device_id": device_id,
        "message": f"Agent reset for device {device_id}",
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
        # Validate incoming configuration to avoid silently falling back to defaults
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
            merge_mode=True,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save config")

        # 同步到环境变量
        config_manager.sync_to_env()
        config.refresh_from_env()

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
