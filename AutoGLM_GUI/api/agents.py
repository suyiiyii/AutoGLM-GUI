"""Agent lifecycle and chat routes."""

import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from AutoGLM_GUI.config import config
from AutoGLM_GUI.config_manager import (
    delete_config_file,
    get_config_path,
    load_config_file,
    save_config_file,
)
from AutoGLM_GUI.schemas import (
    APIAgentConfig,
    APIModelConfig,
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    ConfigSaveRequest,
    InitRequest,
    ResetRequest,
    StatusResponse,
    StopRequest,
)
from AutoGLM_GUI.state import (
    agent_configs,
    agents,
    non_blocking_takeover,
    stop_flags,
)
from AutoGLM_GUI.version import APP_VERSION
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

router = APIRouter()


@router.post("/api/init")
def init_agent(request: InitRequest) -> dict:
    """初始化 PhoneAgent（多设备支持）。"""
    from AutoGLM_GUI.adb_plus import ADBKeyboardInstaller
    from AutoGLM_GUI.logger import logger

    req_model_config = request.model or APIModelConfig()
    req_agent_config = request.agent or APIAgentConfig()

    device_id = req_agent_config.device_id
    if not device_id:
        raise HTTPException(
            status_code=400, detail="device_id is required in agent_config"
        )
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

    agents[device_id] = PhoneAgent(
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
    except Exception as e:
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

    # Reset stop flag at the start of execution
    stop_flags[device_id] = False

    def event_generator():
        """SSE 事件生成器"""
        try:
            step_result = agent.step(request.message)
            while True:
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

                # Check stop flag after each step
                if stop_flags.get(device_id, False):
                    stopped_data = {
                        "type": "stopped",
                        "message": "任务已停止",
                        "steps": agent.step_count,
                    }
                    yield "event: stopped\n"
                    yield f"data: {json.dumps(stopped_data, ensure_ascii=False)}\n\n"
                    break

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
            # Clean up stop flag
            stop_flags.pop(device_id, None)

        except Exception as e:
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


@router.post("/api/chat/stop")
def stop_chat(request: StopRequest) -> dict:
    """停止正在执行的 Agent 任务。"""
    device_id = request.device_id

    if device_id not in agents:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    stop_flags[device_id] = True

    return {
        "success": True,
        "device_id": device_id,
        "message": f"Stop signal sent for device {device_id}",
    }


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
        agents[device_id] = PhoneAgent(
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
    from AutoGLM_GUI.config import config

    # 加载配置文件
    file_config = load_config_file()

    # 读取当前实际运行的配置
    current_base_url = os.getenv("AUTOGLM_BASE_URL", config.base_url)
    current_model_name = os.getenv("AUTOGLM_MODEL_NAME", config.model_name)
    current_api_key = os.getenv("AUTOGLM_API_KEY", config.api_key)

    # 判断配置来源
    # 如果环境变量中有 CLI 参数设置的值，优先级最高
    env_config = {
        "base_url": os.getenv("AUTOGLM_BASE_URL"),
        "model_name": os.getenv("AUTOGLM_MODEL_NAME"),
        "api_key": os.getenv("AUTOGLM_API_KEY"),
    }

    # 检查是否有 CLI 参数（环境变量值不同于默认值且文件配置中没有对应值）
    has_cli_config = (
        (
            (env_config["base_url"] and env_config["base_url"] != "")
            and (
                not file_config or file_config.get("base_url") != env_config["base_url"]
            )
        )
        or (
            (
                env_config["model_name"]
                and env_config["model_name"] != "autoglm-phone-9b"
            )
            and (
                not file_config
                or file_config.get("model_name") != env_config["model_name"]
            )
        )
        or (
            (env_config["api_key"] and env_config["api_key"] != "EMPTY")
            and (not file_config or file_config.get("api_key") != env_config["api_key"])
        )
    )

    if has_cli_config:
        source = "CLI arguments"
    elif file_config:
        source = "config file"
    else:
        source = "default"

    return ConfigResponse(
        base_url=current_base_url,
        model_name=current_model_name,
        api_key=current_api_key if current_api_key != "EMPTY" else "",
        source=source,
    )


@router.post("/api/config")
def save_config_endpoint(request: ConfigSaveRequest) -> dict:
    """保存配置到文件."""
    try:
        config_data = {
            "base_url": request.base_url,
            "model_name": request.model_name,
        }

        # 只有提供了 api_key 才保存
        if request.api_key:
            config_data["api_key"] = request.api_key

        success = save_config_file(config_data)

        if success:
            # 刷新全局配置
            os.environ["AUTOGLM_BASE_URL"] = request.base_url
            os.environ["AUTOGLM_MODEL_NAME"] = request.model_name
            if request.api_key:
                os.environ["AUTOGLM_API_KEY"] = request.api_key
            config.refresh_from_env()

            return {
                "success": True,
                "message": f"Configuration saved to {get_config_path()}",
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save config")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/config")
def delete_config_endpoint() -> dict:
    """删除配置文件."""
    try:
        success = delete_config_file()
        if success:
            return {"success": True, "message": "Configuration deleted"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete config")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
