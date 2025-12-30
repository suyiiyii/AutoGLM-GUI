"""Agent lifecycle and chat routes."""

import json
import queue
import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from AutoGLM_GUI.config import config
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.phone_agent_patches import apply_patches
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
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

# Apply monkey patches to phone_agent
apply_patches()

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


def _initialize_agent_with_config(
    device_id: str,
    model_config: ModelConfig,
    agent_config: AgentConfig,
) -> None:
    """使用给定配置初始化 Agent。

    Args:
        device_id: 设备 ID
        model_config: 模型配置
        agent_config: Agent 配置

    Raises:
        Exception: 初始化失败时抛出异常
    """
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    # Setup ADB Keyboard first
    _setup_adb_keyboard(device_id)

    # Initialize agent
    manager = PhoneAgentManager.get_instance()
    manager.initialize_agent(
        device_id=device_id,
        model_config=model_config,
        agent_config=agent_config,
        takeover_callback=non_blocking_takeover,
    )
    logger.info(f"Agent initialized successfully for device {device_id}")


def _create_sse_event(
    event_type: str, data: dict[str, Any], role: str = "assistant"
) -> dict[str, Any]:
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
    config.refresh_from_env()

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

    # Initialize agent (includes ADB Keyboard setup)
    try:
        # Setup ADB Keyboard (common for all agents)
        _setup_adb_keyboard(device_id)

        # Use agent factory to create agent
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

        manager = PhoneAgentManager.get_instance()

        # Initialize agent using factory pattern
        manager.initialize_agent_with_factory(
            device_id=device_id,
            agent_type=request.agent_type,
            model_config=model_config,
            agent_config=agent_config,
            agent_specific_config=request.agent_config_params or {},
            takeover_callback=non_blocking_takeover,
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
        """SSE 事件生成器."""
        threads: list[threading.Thread] = []

        try:
            # 创建事件队列用于 agent → SSE 通信
            event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

            # 思考块回调
            def on_thinking_chunk(chunk: str):
                chunk_data = _create_sse_event("thinking_chunk", {"chunk": chunk})
                event_queue.put(("thinking_chunk", chunk_data))

            # 使用 streaming agent context manager（自动处理所有管理逻辑！）
            with manager.use_streaming_agent(
                device_id, on_thinking_chunk, timeout=0
            ) as (streaming_agent, stop_event):
                # 早期 abort 检查
                if stop_event.is_set():
                    logger.info(f"[Abort] Chat aborted before starting for {device_id}")
                    yield "event: aborted\n"
                    yield 'data: {"type": "aborted", "role": "assistant", "message": "Chat aborted by user"}\n\n'
                    return

                # 在线程中运行 agent 步骤
                step_result: list[Any] = [None]
                error_result: list[Any] = [None]

                def run_step(is_first: bool = True, task: str | None = None):
                    try:
                        if stop_event.is_set():
                            return

                        result = (
                            streaming_agent.step(task)
                            if is_first
                            else streaming_agent.step()
                        )

                        if stop_event.is_set():
                            return

                        step_result[0] = result
                    except Exception as e:
                        error_result[0] = e
                    finally:
                        event_queue.put(("step_done", None))

                # 启动第一步
                thread = threading.Thread(
                    target=run_step, args=(True, request.message), daemon=True
                )
                thread.start()
                threads.append(thread)

                # 事件循环
                while not stop_event.is_set():
                    try:
                        event_type, event_data = event_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if event_type == "thinking_chunk":
                        yield "event: thinking_chunk\n"
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    elif event_type == "step_done":
                        if error_result[0]:
                            raise error_result[0]

                        result = step_result[0]
                        event_data = _create_sse_event(
                            "step",
                            {
                                "step": streaming_agent.step_count,
                                "thinking": result.thinking,
                                "action": result.action,
                                "success": result.success,
                                "finished": result.finished,
                            },
                        )

                        yield "event: step\n"
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                        if result.finished:
                            done_data = _create_sse_event(
                                "done",
                                {
                                    "message": result.message,
                                    "steps": streaming_agent.step_count,
                                    "success": result.success,
                                },
                            )
                            yield "event: done\n"
                            yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                            break

                        if (
                            streaming_agent.step_count
                            >= streaming_agent.agent_config.max_steps
                        ):
                            done_data = _create_sse_event(
                                "done",
                                {
                                    "message": "Max steps reached",
                                    "steps": streaming_agent.step_count,
                                    "success": result.success,
                                },
                            )
                            yield "event: done\n"
                            yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                            break

                        # 启动下一步
                        step_result[0] = None
                        error_result[0] = None
                        thread = threading.Thread(
                            target=run_step, args=(False, None), daemon=True
                        )
                        thread.start()
                        threads.append(thread)

                # 检查是否被中止
                if stop_event.is_set():
                    logger.info(f"[Abort] Streaming chat terminated for {device_id}")
                    yield "event: aborted\n"
                    yield 'data: {"type": "aborted", "role": "assistant", "message": "Chat aborted by user"}\n\n'

                # 重置原始 agent（context 已由 use_streaming_agent 同步）
                original_agent = manager.get_agent(device_id)
                original_agent.reset()

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
            # 通知线程停止
            if "stop_event" in locals():
                stop_event.set()

            # 等待线程完成（带超时）
            for thread in threads:
                if thread.is_alive():
                    thread.join(timeout=5.0)

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
        dual_model_enabled=effective_config.dual_model_enabled,
        decision_base_url=effective_config.decision_base_url,
        decision_model_name=effective_config.decision_model_name,
        decision_api_key=effective_config.decision_api_key
        if effective_config.decision_api_key
        else "",
        agent_type=effective_config.agent_type,
        agent_config_params=effective_config.agent_config_params,
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
            dual_model_enabled=request.dual_model_enabled,
            decision_base_url=request.decision_base_url,
            decision_model_name=request.decision_model_name,
            decision_api_key=request.decision_api_key,
            agent_type=request.agent_type,
            agent_config_params=request.agent_config_params,
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
