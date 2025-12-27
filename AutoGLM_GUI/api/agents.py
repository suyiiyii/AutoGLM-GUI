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
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

# Apply monkey patches to phone_agent
apply_patches()

router = APIRouter()

# Active chat sessions (device_id -> stop_event)
# Used for aborting ongoing conversations
_active_chats: dict[str, threading.Event] = {}
_active_chats_lock = threading.Lock()


def _release_device_lock_when_done(
    device_id: str, threads: list[threading.Thread]
) -> None:
    """Block until threads finish, then release the device lock via manager."""
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    for thread in threads:
        thread.join()

    manager = PhoneAgentManager.get_instance()
    manager.release_device(device_id)


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

    # Initialize agent via PhoneAgentManager (thread-safe, transactional)
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    manager = PhoneAgentManager.get_instance()
    try:
        manager.initialize_agent(
            device_id=device_id,
            model_config=model_config,
            agent_config=agent_config,
            takeover_callback=non_blocking_takeover,
        )
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "device_id": device_id,
        "message": f"Agent initialized for device {device_id}",
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
    from AutoGLM_GUI.exceptions import AgentNotInitializedError, DeviceBusyError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    manager = PhoneAgentManager.get_instance()

    # Check if agent is initialized
    if not manager.is_initialized(device_id):
        raise HTTPException(
            status_code=400,
            detail=f"Device {device_id} not initialized. Call /api/init first.",
        )

    # Acquire device lock (non-blocking) to prevent concurrent requests
    try:
        manager.acquire_device(device_id, timeout=0, raise_on_timeout=True)
    except DeviceBusyError:
        raise HTTPException(
            status_code=409,
            detail=f"Device {device_id} is already processing a request. Please wait.",
        )

    try:
        # Get the original agent to copy its config
        original_agent = manager.get_agent(device_id)

        # Get the stored configs for this device
        try:
            model_config, agent_config = manager.get_config(device_id)
        except AgentNotInitializedError:
            manager.release_device(device_id)
            raise HTTPException(
                status_code=400,
                detail=f"Device {device_id} config not found.",
            )

        def event_generator():
            """SSE 事件生成器"""
            threads: list[threading.Thread] = []
            stop_event = threading.Event()

            # Register stop_event to global mapping for abort support
            with _active_chats_lock:
                _active_chats[device_id] = stop_event

            try:
                # Create a queue to collect events from the agent
                event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

                # Create a callback to handle thinking chunks
                def on_thinking_chunk(chunk: str):
                    """Emit thinking chunks as they arrive"""
                    if not stop_event.is_set():
                        chunk_data = {
                            "type": "thinking_chunk",
                            "chunk": chunk,
                        }
                        event_queue.put(("thinking_chunk", chunk_data))

                # Create a new agent instance
                streaming_agent = PhoneAgent(
                    model_config=model_config,
                    agent_config=agent_config,
                    takeover_callback=non_blocking_takeover,
                )

                # Copy context from original agent (thread-safe due to device lock)
                streaming_agent._context = original_agent._context.copy()
                streaming_agent._step_count = original_agent._step_count

                # Monkey-patch the model_client.request to inject the callback
                original_request = streaming_agent.model_client.request

                def patched_request(messages, **kwargs):
                    # Inject the on_thinking_chunk callback
                    return original_request(
                        messages, on_thinking_chunk=on_thinking_chunk
                    )

                streaming_agent.model_client.request = patched_request

                # Early abort check (before starting any steps)
                if stop_event.is_set():
                    logger.info(
                        f"[Abort] Agent for device {device_id} received abort signal before starting steps"
                    )
                    yield "event: aborted\n"
                    yield 'data: {"type": "aborted", "message": "Chat aborted by user"}\n\n'
                    return

                # Run agent step in a separate thread
                step_result: list[Any] = [None]
                error_result: list[Any] = [None]

                def run_step(is_first: bool = True, task: str | None = None):
                    try:
                        # Check before starting step
                        if stop_event.is_set():
                            logger.info(
                                f"[Abort] Agent for device {device_id} received abort signal before step execution"
                            )
                            return

                        if is_first:
                            result = streaming_agent.step(task)
                        else:
                            result = streaming_agent.step()

                        # Check after step completes
                        if stop_event.is_set():
                            logger.info(
                                f"[Abort] Agent for device {device_id} received abort signal after step execution"
                            )
                            return

                        step_result[0] = result
                    except Exception as e:
                        error_result[0] = e
                    finally:
                        event_queue.put(("step_done", None))

                # Start first step
                thread = threading.Thread(
                    target=run_step, args=(True, request.message), daemon=True
                )
                thread.start()
                threads.append(thread)

                while not stop_event.is_set():
                    # Wait for events from the queue
                    try:
                        event_type, event_data = event_queue.get(timeout=0.1)
                    except queue.Empty:
                        # Check again on timeout
                        if stop_event.is_set():
                            break
                        continue

                    if event_type == "thinking_chunk":
                        yield "event: thinking_chunk\n"
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    elif event_type == "step_done":
                        # Check for errors
                        if error_result[0]:
                            raise error_result[0]

                        result = step_result[0]
                        event_data = {
                            "type": "step",
                            "step": streaming_agent.step_count,
                            "thinking": result.thinking,
                            "action": result.action,
                            "success": result.success,
                            "finished": result.finished,
                        }

                        yield "event: step\n"
                        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                        if result.finished:
                            done_data = {
                                "type": "done",
                                "message": result.message,
                                "steps": streaming_agent.step_count,
                                "success": result.success,
                            }
                            yield "event: done\n"
                            yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                            break

                        if (
                            streaming_agent.step_count
                            >= streaming_agent.agent_config.max_steps
                        ):
                            done_data = {
                                "type": "done",
                                "message": "Max steps reached",
                                "steps": streaming_agent.step_count,
                                "success": result.success,
                            }
                            yield "event: done\n"
                            yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                            break

                        # Start next step
                        step_result[0] = None
                        error_result[0] = None
                        thread = threading.Thread(
                            target=run_step, args=(False, None), daemon=True
                        )
                        thread.start()
                        threads.append(thread)

                # Check if loop exited due to abort
                if stop_event.is_set():
                    logger.info(
                        f"[Abort] Agent for device {device_id} event loop terminated due to abort signal"
                    )
                    yield "event: aborted\n"
                    yield 'data: {"type": "aborted", "message": "Chat aborted by user"}\n\n'

                # Update original agent state (thread-safe due to device lock)
                original_agent._context = streaming_agent._context
                original_agent._step_count = streaming_agent._step_count

                original_agent.reset()

            except Exception as e:
                error_data = {
                    "type": "error",
                    "message": str(e),
                }
                yield "event: error\n"
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            finally:
                # Clean up active chats mapping
                with _active_chats_lock:
                    _active_chats.pop(device_id, None)

                # Signal all threads to stop
                stop_event.set()

                alive_threads = [thread for thread in threads if thread.is_alive()]
                if alive_threads:
                    # Release lock after background threads complete
                    cleanup_thread = threading.Thread(
                        target=_release_device_lock_when_done,
                        args=(device_id, alive_threads),
                        daemon=True,
                    )
                    cleanup_thread.start()
                else:
                    # Release lock immediately if no threads are alive
                    manager.release_device(device_id)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:
        # Release lock if exception occurs before generator starts
        manager.release_device(device_id)
        raise


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
    from AutoGLM_GUI.logger import logger

    device_id = request.device_id

    with _active_chats_lock:
        if device_id in _active_chats:
            logger.info(f"Aborting chat for device {device_id}")
            _active_chats[device_id].set()  # 设置中断标志
            return {"success": True, "message": "Abort requested"}
        else:
            logger.warning(f"No active chat found for device {device_id}")
            return {"success": False, "message": "No active chat found"}


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
