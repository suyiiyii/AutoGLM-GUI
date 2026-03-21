"""Agent lifecycle and chat routes."""

import asyncio
import json

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from AutoGLM_GUI.schemas import (
    AbortRequest,
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    ConfigSaveRequest,
    ResetRequest,
    StatusResponse,
)
from AutoGLM_GUI.version import APP_VERSION

router = APIRouter()


SSEPayload = dict[str, Any]


def _create_sse_event(
    event_type: str, data: SSEPayload, role: str = "assistant"
) -> SSEPayload:
    """Create an SSE event with standardized fields including role."""
    event_data = {"type": event_type, "role": role, **data}
    return event_data


def _resolve_device_serial(device_id: str) -> str:
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    return device_manager.get_serial_by_device_id(device_id) or device_id


async def _create_legacy_chat_task(request: ChatRequest) -> dict[str, Any]:
    from AutoGLM_GUI.task_manager import task_manager

    session = await task_manager.get_or_create_legacy_chat_session(
        device_id=request.device_id,
        device_serial=_resolve_device_serial(request.device_id),
    )
    return await task_manager.submit_chat_task(
        session_id=str(session["id"]),
        device_id=request.device_id,
        device_serial=str(session["device_serial"]),
        message=request.message,
    )


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Compatibility wrapper around the new task-backed chat flow."""
    from AutoGLM_GUI.task_manager import task_manager
    from AutoGLM_GUI.task_store import TaskStatus

    task = await _create_legacy_chat_task(request)
    final_task = await task_manager.wait_for_task(task["id"])
    if final_task is None:
        raise HTTPException(status_code=500, detail="Task disappeared unexpectedly")

    success = final_task["status"] == TaskStatus.SUCCEEDED.value
    message = (
        final_task.get("final_message")
        or final_task.get("error_message")
        or final_task["status"]
    )
    return ChatResponse(
        result=str(message),
        steps=int(final_task.get("step_count", 0)),
        success=success,
    )


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Compatibility SSE endpoint backed by the new task event stream."""
    from AutoGLM_GUI.task_store import TERMINAL_TASK_STATUSES, task_store

    task = await _create_legacy_chat_task(request)

    async def event_generator():
        last_seq = 0
        while True:
            events = await asyncio.to_thread(
                task_store.list_task_events,
                task["id"],
                after_seq=last_seq,
            )
            for event in events:
                last_seq = int(event["seq"])
                event_type = str(event["event_type"])
                if event_type == "status":
                    continue
                sse_event = _create_sse_event(
                    event_type,
                    dict(event["payload"]),
                    role=str(event["role"]),
                )
                yield f"event: {event_type}\n"
                yield f"data: {json.dumps(sse_event, ensure_ascii=False)}\n\n"

            current_task = await asyncio.to_thread(task_store.get_task, task["id"])
            if (
                current_task is None or current_task["status"] in TERMINAL_TASK_STATUSES
            ) and not events:
                break
            await asyncio.sleep(0.2)

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
def reset_agent(request: ResetRequest) -> dict[str, Any]:
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
async def abort_chat(request: AbortRequest) -> dict[str, Any]:
    """Cancel the latest active task for the device."""
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
    from AutoGLM_GUI.task_manager import task_manager
    from AutoGLM_GUI.task_store import TERMINAL_TASK_STATUSES, TaskStatus

    task = await task_manager.cancel_latest_chat_task(request.device_id)
    success = task is not None and (
        task["status"] not in TERMINAL_TASK_STATUSES
        or task["status"] == TaskStatus.CANCELLED.value
    )
    if not success:
        success = await PhoneAgentManager.get_instance().abort_streaming_chat_async(
            request.device_id
        )

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
        layered_max_turns=effective_config.layered_max_turns,
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
def save_config_endpoint(request: ConfigSaveRequest) -> dict[str, Any]:
    """保存配置到文件.

    配置保存后需重启应用以立即生效。
    """
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
            layered_max_turns=request.layered_max_turns,
            decision_base_url=request.decision_base_url,
            decision_model_name=request.decision_model_name,
            decision_api_key=request.decision_api_key,
            merge_mode=True,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save config")

        # 同步到环境变量
        config_manager.sync_to_env()

        # 检测冲突并返回警告
        conflicts = config_manager.detect_conflicts()

        response_message = (
            f"Configuration saved to {config_manager.get_config_path()}."
            " Restart required to apply new configuration immediately."
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
                "restart_required": True,
            }

        return {
            "success": True,
            "message": response_message,
            "restart_required": True,
        }

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/config")
def delete_config_endpoint() -> dict[str, Any]:
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
