"""双模型协作API端点"""

import threading
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.dual_model import (
    DecisionModelConfig,
    DualModelAgent,
    DualModelEvent,
    DualModelEventType,
)
from AutoGLM_GUI.dual_model.protocols import ThinkingMode
from phone_agent.model import ModelConfig

router = APIRouter(prefix="/api/dual", tags=["dual-model"])

# 活跃的双模型会话 (device_id -> (agent, stop_event))
_active_dual_sessions: dict[str, tuple[DualModelAgent, threading.Event]] = {}
_active_dual_sessions_lock = threading.Lock()


class DualModelInitRequest(BaseModel):
    """双模型初始化请求"""

    device_id: str

    # 决策大模型配置
    decision_base_url: str
    decision_api_key: str
    decision_model_name: str

    # 视觉小模型配置(复用现有配置)
    vision_base_url: Optional[str] = None
    vision_api_key: Optional[str] = None
    vision_model_name: Optional[str] = None

    max_steps: int = 50
    thinking_mode: str = "deep"  # fast, deep, turbo


class DualModelChatRequest(BaseModel):
    """双模型聊天请求"""

    device_id: str
    message: str


class DualModelAbortRequest(BaseModel):
    """中止请求"""

    device_id: str


class DualModelStatusResponse(BaseModel):
    """状态响应"""

    active: bool
    device_id: Optional[str] = None
    state: Optional[dict] = None


@router.post("/init")
def init_dual_model(request: DualModelInitRequest) -> dict:
    """初始化双模型Agent"""
    from AutoGLM_GUI.config import config
    from AutoGLM_GUI.config_manager import config_manager
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_id = request.device_id
    thinking_mode_map = {
        "fast": ThinkingMode.FAST,
        "deep": ThinkingMode.DEEP,
        "turbo": ThinkingMode.TURBO,
    }
    thinking_mode = thinking_mode_map.get(request.thinking_mode, ThinkingMode.DEEP)
    logger.info(f"初始化双模型Agent: {device_id}, 模式: {thinking_mode.value}")

    # 检查设备是否已有单模型Agent初始化
    manager = PhoneAgentManager.get_instance()
    if not manager.is_initialized(device_id):
        raise HTTPException(
            status_code=400, detail="设备尚未初始化单模型Agent，请先调用 /api/init"
        )

    # 获取视觉模型配置
    vision_base_url = request.vision_base_url or config.base_url
    vision_api_key = request.vision_api_key or config.api_key
    vision_model_name = request.vision_model_name or config.model_name

    if not vision_base_url:
        raise HTTPException(status_code=400, detail="视觉模型base_url未配置")

    # 获取配置的默认最大步数
    effective_config = config_manager.get_effective_config()
    max_steps = effective_config.default_max_steps

    # 创建配置
    decision_config = DecisionModelConfig(
        base_url=request.decision_base_url,
        api_key=request.decision_api_key,
        model_name=request.decision_model_name,
        thinking_mode=thinking_mode,
    )

    vision_config = ModelConfig(
        base_url=vision_base_url,
        api_key=vision_api_key,
        model_name=vision_model_name,
    )

    # 创建双模型Agent
    try:
        agent = DualModelAgent(
            decision_config=decision_config,
            vision_config=vision_config,
            device_id=device_id,
            max_steps=max_steps,
            thinking_mode=thinking_mode,
        )

        # 存储到活跃会话
        with _active_dual_sessions_lock:
            # 清理旧会话
            if device_id in _active_dual_sessions:
                old_agent, old_event = _active_dual_sessions[device_id]
                old_event.set()

            _active_dual_sessions[device_id] = (agent, threading.Event())

        logger.info(f"双模型Agent初始化成功: {device_id}")

        return {
            "success": True,
            "device_id": device_id,
            "message": "双模型Agent初始化成功",
            "decision_model": request.decision_model_name,
            "vision_model": vision_model_name,
            "thinking_mode": thinking_mode.value,
        }

    except Exception as e:
        logger.error(f"双模型Agent初始化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
def dual_model_chat_stream(request: DualModelChatRequest):
    """双模型聊天(SSE流式)"""
    device_id = request.device_id

    with _active_dual_sessions_lock:
        if device_id not in _active_dual_sessions:
            raise HTTPException(
                status_code=400, detail="双模型Agent未初始化，请先调用 /api/dual/init"
            )
        agent, stop_event = _active_dual_sessions[device_id]

    # 重置停止事件
    stop_event.clear()

    def event_generator():
        """SSE事件生成器"""
        try:
            logger.info(f"开始双模型任务: {request.message[:50]}...")

            # 在后台线程运行Agent
            result_holder: list[Any] = [None]
            error_holder: list[Any] = [None]

            def run_agent():
                try:
                    result = agent.run(request.message)
                    result_holder[0] = result
                except Exception as e:
                    error_holder[0] = e

            thread = threading.Thread(target=run_agent, daemon=True)
            thread.start()

            # 持续发送事件
            while thread.is_alive() or not agent.event_queue.empty():
                if stop_event.is_set():
                    agent.abort()
                    yield "event: aborted\n"
                    yield 'data: {"type": "aborted", "message": "任务被用户中断"}\n\n'
                    break

                # 获取事件
                try:
                    events = agent.get_events(timeout=0.1)
                    for event in events:
                        yield event.to_sse()

                        # 如果是完成或错误事件，结束循环
                        if event.type in [
                            DualModelEventType.TASK_COMPLETE,
                            DualModelEventType.ERROR,
                        ]:
                            return
                except Exception:
                    continue

            # 等待线程完成
            thread.join(timeout=5)

            # 检查错误
            if error_holder[0]:
                error_event = DualModelEvent(
                    type=DualModelEventType.ERROR,
                    data={"message": str(error_holder[0])},
                )
                yield error_event.to_sse()

            # 如果没有发送完成事件，发送一个
            if result_holder[0] and not stop_event.is_set():
                result = result_holder[0]
                if isinstance(result, dict):
                    done_event = DualModelEvent(
                        type=DualModelEventType.TASK_COMPLETE,
                        data={
                            "success": result.get("success", False),
                            "message": result.get("message", ""),
                            "steps": result.get("steps", 0),
                        },
                    )
                    yield done_event.to_sse()

        except Exception as e:
            logger.exception(f"双模型任务异常: {e}")
            error_event = DualModelEvent(
                type=DualModelEventType.ERROR,
                data={"message": str(e)},
            )
            yield error_event.to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/abort")
def abort_dual_model_chat(request: DualModelAbortRequest) -> dict:
    """中止双模型聊天"""
    device_id = request.device_id

    with _active_dual_sessions_lock:
        if device_id in _active_dual_sessions:
            agent, stop_event = _active_dual_sessions[device_id]
            stop_event.set()
            agent.abort()
            logger.info(f"双模型任务已中止: {device_id}")
            return {"success": True, "message": "已发送中止信号"}
        else:
            return {"success": False, "message": "未找到活跃的双模型会话"}


@router.get("/status")
def get_dual_model_status(device_id: Optional[str] = None) -> DualModelStatusResponse:
    """获取双模型状态"""
    with _active_dual_sessions_lock:
        if device_id:
            if device_id in _active_dual_sessions:
                agent, _ = _active_dual_sessions[device_id]
                return DualModelStatusResponse(
                    active=True,
                    device_id=device_id,
                    state=agent.get_state(),
                )
            else:
                return DualModelStatusResponse(active=False, device_id=device_id)
        else:
            # 返回所有活跃会话
            return DualModelStatusResponse(
                active=len(_active_dual_sessions) > 0,
                state={"active_devices": list(_active_dual_sessions.keys())},
            )


@router.post("/reset")
def reset_dual_model(request: DualModelAbortRequest) -> dict:
    """重置双模型Agent"""
    device_id = request.device_id

    with _active_dual_sessions_lock:
        if device_id in _active_dual_sessions:
            agent, stop_event = _active_dual_sessions[device_id]
            stop_event.set()
            agent.reset()
            logger.info(f"双模型Agent已重置: {device_id}")
            return {"success": True, "message": "双模型Agent已重置"}
        else:
            return {"success": False, "message": "未找到双模型会话"}


@router.delete("/session/{device_id}")
def delete_dual_model_session(device_id: str) -> dict:
    """删除双模型会话"""
    with _active_dual_sessions_lock:
        if device_id in _active_dual_sessions:
            agent, stop_event = _active_dual_sessions.pop(device_id)
            stop_event.set()
            logger.info(f"双模型会话已删除: {device_id}")
            return {"success": True, "message": "双模型会话已删除"}
        else:
            return {"success": False, "message": "未找到双模型会话"}
