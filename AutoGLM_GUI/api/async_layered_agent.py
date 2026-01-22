"""Async Layered Agent API - 异步分层代理实现。

这是 layered_agent.py 的异步版本，核心改进：
1. 执行层使用 AsyncGLMAgent，真正的端到端异步
2. 支持立即取消（<1s），无需等待 agent.run() 完成
3. 零阻塞 I/O，所有网络请求都是异步的

架构：
- 决策层：openai-agents SDK (AsyncOpenAI)
- 执行层：AsyncGLMAgent (AsyncOpenAI)
- 工具：async_list_devices, async_chat

与同步版本的区别：
- 同步版本：asyncio.to_thread(_sync_chat) -> agent.run() [阻塞]
- 异步版本：await agent.run() [真正异步]

API 端点：
- POST /api/async-layered-agent/chat - 异步聊天（SSE 流）
- POST /api/async-layered-agent/abort - 取消执行
- POST /api/async-layered-agent/reset - 重置 session

Session 管理：
- 每个 session_id 持有独立的 SQLiteSession 和 agents 字典
- agents 懒加载：首次调用 chat(device_id) 时创建
- reset 时清理所有 agents

Author: AutoGLM Team
Date: 2026-01-22
"""

import asyncio
import json
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any, AsyncGenerator

from agents import Agent, Runner, SQLiteSession, function_tool

if TYPE_CHECKING:
    from agents.result import RunResultStreaming

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from AutoGLM_GUI.agents.glm.async_agent import AsyncGLMAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.config_manager import config_manager
from AutoGLM_GUI.device_manager import DeviceManager
from AutoGLM_GUI.history_manager import history_manager
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.models.history import ConversationRecord
from AutoGLM_GUI.prompts import MCP_SYSTEM_PROMPT_ZH

# 从同步版本导入 PLANNER_INSTRUCTIONS
from AutoGLM_GUI.api.layered_agent import PLANNER_INSTRUCTIONS

router = APIRouter()

# ==================== Session 管理 ====================
# 存储每个 session_id 对应的 SQLiteSession 和 agents
_async_sessions: dict[str, dict[str, Any]] = {}
# 结构示例：
# {
#   "session_123": {
#       "sqlite_session": SQLiteSession("session_123"),
#       "agents": {
#           "device_001": AsyncGLMAgent(...),
#           "device_002": AsyncGLMAgent(...)
#       }
#   }
# }

# ==================== 活跃运行管理 ====================
# 存储每个 session_id 对应的活跃 RunResultStreaming 实例，用于 abort
_async_active_runs: dict[str, "RunResultStreaming"] = {}
_async_active_runs_lock = threading.Lock()

# ==================== 全局 Planner Agent ====================
_async_client: AsyncOpenAI | None = None
_async_agent: Agent[Any] | None = None
_async_cached_config_hash: str | None = None


# ==================== Helper Functions ====================
def _get_or_create_async_session(session_id: str) -> SQLiteSession:
    """获取或创建指定 session_id 的 session。

    如果 session 不存在，创建新的 session 和空的 agents 字典。

    Args:
        session_id: Session 标识符

    Returns:
        SQLiteSession: 该 session 的 SQLiteSession 实例
    """
    if session_id not in _async_sessions:
        _async_sessions[session_id] = {
            "sqlite_session": SQLiteSession(session_id),
            "agents": {},
        }
        logger.info(f"[AsyncLayeredAgent] Created new session: {session_id}")

    return _async_sessions[session_id]["sqlite_session"]


def _compute_config_hash() -> str:
    """计算当前配置的哈希值，用于检测配置变化。

    Returns:
        str: 配置的 MD5 哈希值
    """
    import hashlib

    config = config_manager.get_effective_config()
    config_str = config.model_dump_json()
    return hashlib.md5(config_str.encode()).hexdigest()


def _setup_async_openai_client() -> AsyncOpenAI:
    """设置异步 OpenAI 客户端，使用决策模型配置。

    Returns:
        AsyncOpenAI: 配置好的异步客户端

    Raises:
        ValueError: 决策模型配置缺失
    """
    config_manager.load_file_config()
    effective_config = config_manager.get_effective_config()

    # 检查决策模型配置
    decision_base_url = effective_config.decision_base_url
    decision_api_key = effective_config.decision_api_key

    if not decision_base_url:
        raise ValueError(
            "决策模型 Base URL 未配置。使用分层代理模式需要配置决策模型。\n"
            "请在全局配置中设置决策模型的 Base URL、模型名称和 API Key。"
        )

    # decision_api_key 可以为 None（某些本地模型不需要）
    decision_model_name = effective_config.decision_model_name
    if not decision_model_name:
        raise ValueError(
            "决策模型名称未配置。使用分层代理模式需要配置决策模型。\n"
            "请在全局配置中设置决策模型的 Base URL、模型名称和 API Key。"
        )

    logger.info("[AsyncLayeredAgent] Decision model config:")
    logger.info(f"  - Base URL: {decision_base_url}")
    logger.info(f"  - Model: {decision_model_name}")
    logger.info(f"  - API Key: {'***' if decision_api_key else 'None'}")

    return AsyncOpenAI(
        base_url=decision_base_url,
        api_key=decision_api_key or "EMPTY",  # 某些本地模型需要非空字符串
    )


# ==================== Tool Functions ====================
def _sync_list_devices() -> str:
    """同步实现：获取所有连接的 ADB 设备列表。

    Returns:
        str: JSON 格式的设备列表
    """
    from AutoGLM_GUI.api.devices import _build_device_response_with_agent
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    logger.info("[AsyncLayeredAgent] list_devices tool called")

    device_manager = DeviceManager.get_instance()
    agent_manager = PhoneAgentManager.get_instance()

    # 如果轮询未启动，执行同步刷新
    if not device_manager._poll_thread or not device_manager._poll_thread.is_alive():
        logger.warning("Polling not started, performing sync refresh")
        device_manager.force_refresh()

    managed_devices = device_manager.get_devices()

    # 构建设备响应
    devices_with_agents = [
        _build_device_response_with_agent(d, agent_manager) for d in managed_devices
    ]

    # Convert DeviceResponse Pydantic models to dicts before JSON serialization
    devices_dict = [device.model_dump() for device in devices_with_agents]
    return json.dumps(devices_dict, ensure_ascii=False, indent=2)


@function_tool
async def async_list_devices() -> str:
    """获取所有连接的 ADB 设备列表。

    返回设备信息包括:
    - id: 设备标识符，用于 chat 工具调用
    - model: 设备型号
    - status: 连接状态
    - connection_type: 连接类型 (usb/wifi/remote)

    Returns:
        JSON 格式的设备列表
    """
    return await asyncio.to_thread(_sync_list_devices)


@function_tool
async def async_chat(device_id: str, message: str) -> str:
    """向指定设备的 Phone Agent 发送子任务指令。

    Phone Agent 是一个视觉模型，能够看到手机屏幕并执行操作。
    每次调用会执行一个原子化的子任务（最多 5 步操作）。

    使用 AsyncGLMAgent 实现真正的异步执行。

    Args:
        device_id: 设备标识符，从 list_devices 获取
        message: 子任务指令，例如 "打开微信"、"点击搜索按钮"

    Returns:
        JSON 格式的执行结果，包含:
        - result: 执行结果描述
        - steps: 执行的步数
        - success: 是否成功
    """
    # TODO: 从 Runner 上下文传递 session_id
    # 当前暂时使用 device_id 作为 session_id
    session_id = device_id

    logger.info(
        f"[AsyncLayeredAgent] async_chat tool called: "
        f"device_id={device_id}, message={message}"
    )

    try:
        # 获取或创建 AsyncGLMAgent
        agent = _get_or_create_async_agent(session_id, device_id)

        # 真正的异步调用，带超时保护
        result = await asyncio.wait_for(agent.run(message), timeout=60.0)

        return json.dumps(
            {"result": result, "steps": agent.step_count, "success": True},
            ensure_ascii=False,
        )

    except asyncio.TimeoutError:
        logger.warning(
            f"[AsyncLayeredAgent] Agent execution timeout for device {device_id}"
        )
        # 尝试获取 agent 的步数（如果 agent 已创建）
        steps = 0
        if (
            session_id in _async_sessions
            and device_id in _async_sessions[session_id]["agents"]
        ):
            steps = _async_sessions[session_id]["agents"][device_id].step_count

        return json.dumps(
            {"result": "Execution timeout (60s)", "steps": steps, "success": False},
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"[AsyncLayeredAgent] async_chat tool error: {e}")
        return json.dumps(
            {"result": str(e), "steps": 0, "success": False}, ensure_ascii=False
        )


# ==================== Agent Creation Functions ====================
def _create_async_planner_agent(client: AsyncOpenAI) -> Agent[Any]:
    """创建规划 Agent，使用 Chat Completions API。

    Args:
        client: AsyncOpenAI 客户端

    Returns:
        Agent: 配置好的 planner agent
    """
    effective_config = config_manager.get_effective_config()
    planner_model = effective_config.decision_model_name

    model = OpenAIChatCompletionsModel(
        model=planner_model,
        openai_client=client,
    )

    return Agent(
        name="AsyncPlanner",
        instructions=PLANNER_INSTRUCTIONS,
        model=model,
        tools=[async_list_devices, async_chat],
    )


def _ensure_async_agent() -> Agent[Any]:
    """确保 planner agent 初始化，支持配置热加载。

    检查配置哈希，如果配置变化则重新创建 agent。

    Returns:
        Agent: 全局 planner agent

    Raises:
        ValueError: 配置缺失
    """
    global _async_client, _async_agent, _async_cached_config_hash

    current_hash = _compute_config_hash()

    if _async_agent is None or _async_cached_config_hash != current_hash:
        if _async_agent is not None and _async_cached_config_hash != current_hash:
            logger.info(
                f"[AsyncLayeredAgent] Config changed "
                f"(hash: {_async_cached_config_hash} -> {current_hash}), "
                f"reloading agent..."
            )

        _async_client = _setup_async_openai_client()
        _async_agent = _create_async_planner_agent(_async_client)
        _async_cached_config_hash = current_hash
        logger.info(
            f"[AsyncLayeredAgent] Agent initialized/reloaded "
            f"with config hash: {current_hash}"
        )

    return _async_agent


def _get_or_create_async_agent(session_id: str, device_id: str) -> AsyncGLMAgent:
    """获取或创建指定 session 和 device 的 AsyncGLMAgent。

    懒加载模式：
    1. 如果 session 不存在，先创建 session
    2. 如果 session 存在但没有该 device 的 agent，创建 agent
    3. 否则返回已存在的 agent

    Args:
        session_id: Session 标识符
        device_id: 设备标识符

    Returns:
        AsyncGLMAgent: 该 session+device 的 agent 实例

    Raises:
        ValueError: Device 不存在或 agent 创建失败
    """
    # 确保 session 存在
    if session_id not in _async_sessions:
        _async_sessions[session_id] = {
            "sqlite_session": SQLiteSession(session_id),
            "agents": {},
        }
        logger.info(f"[AsyncLayeredAgent] Created new session: {session_id}")

    # 确保 agent 存在
    agents = _async_sessions[session_id]["agents"]
    if device_id not in agents:
        try:
            # 获取配置
            config = config_manager.get_effective_config()
            model_config = ModelConfig(
                base_url=config.base_url,
                api_key=config.api_key,
                model_name=config.model_name,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                frequency_penalty=config.frequency_penalty,
                extra_body=config.extra_body,
            )

            agent_config = AgentConfig(
                max_steps=5,  # MCP 固定 5 步
                system_prompt=MCP_SYSTEM_PROMPT_ZH,
                verbose=config.verbose,
                lang=config.lang,
            )

            # 获取 device
            device_manager = DeviceManager.get_instance()
            device = device_manager.get_device(device_id)
            if device is None:
                raise ValueError(f"Device {device_id} not found or offline")

            # 创建 agent
            agents[device_id] = AsyncGLMAgent(
                model_config=model_config,
                agent_config=agent_config,
                device=device,
            )
            logger.info(
                f"[AsyncLayeredAgent] Created AsyncGLMAgent for "
                f"session={session_id}, device={device_id}"
            )

        except Exception as e:
            logger.error(f"[AsyncLayeredAgent] Failed to create agent: {e}")
            # 清理部分创建的状态
            if device_id in agents:
                del agents[device_id]
            raise ValueError(f"Failed to create agent for device {device_id}: {e}")

    return agents[device_id]


# ==================== Request/Response Models ====================
class LayeredAgentRequest(BaseModel):
    """Request for async layered agent chat."""

    message: str
    device_id: str | None = None
    session_id: str | None = None  # 用于保持对话上下文，前端可传入 deviceId


class AbortSessionRequest(BaseModel):
    """Request for aborting a running session."""

    session_id: str


class ResetSessionRequest(BaseModel):
    """Request for resetting a session."""

    session_id: str


# ==================== API Endpoints ====================
@router.post("/api/async-layered-agent/chat")
async def async_layered_agent_chat(
    request: LayeredAgentRequest,
) -> StreamingResponse:
    """异步分层代理聊天 API with streaming execution steps.

    使用决策模型进行规划，AsyncGLMAgent 执行。

    Returns SSE stream with events:
    - tool_call: Agent is calling a tool (with tool_name and tool_args)
    - tool_result: Tool execution result
    - message: Intermediate message from agent
    - done: Final response
    - error: Error occurred
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        start_time = datetime.now()
        final_output = ""
        final_success = False

        try:
            agent = _ensure_async_agent()

            session_id = request.session_id or request.device_id or "default"
            session = _get_or_create_async_session(session_id)

            effective_config = config_manager.get_effective_config()

            result = Runner.run_streamed(
                agent,
                request.message,
                max_turns=effective_config.layered_max_turns,
                session=session,
            )

            # 保存活跃运行实例，用于 abort
            with _async_active_runs_lock:
                _async_active_runs[session_id] = result

            current_tool_call: dict[str, Any] | None = None

            try:
                async for event in result.stream_events():
                    if isinstance(event, RawResponsesStreamEvent):
                        # Raw response chunk - could contain thinking
                        pass

                    elif isinstance(event, RunItemStreamEvent):
                        item = event.item

                        # Handle different item types
                        item_type = getattr(item, "type", None)

                        if item_type == "tool_call_item":
                            # Tool call started - extract name from raw_item
                            tool_name = "unknown"
                            tool_args: dict[str, Any] = {}

                            # Try to get from raw_item
                            if hasattr(item, "raw_item") and item.raw_item:
                                raw = item.raw_item

                                # Handle dict format
                                if isinstance(raw, dict):
                                    tool_name = raw.get(
                                        "name",
                                        raw.get("function", {}).get("name", "unknown"),
                                    )
                                    args_str = raw.get(
                                        "arguments",
                                        raw.get("function", {}).get("arguments", "{}"),
                                    )
                                    try:
                                        tool_args = (
                                            json.loads(args_str)
                                            if isinstance(args_str, str)
                                            else args_str
                                        )
                                    except Exception:
                                        tool_args = {"raw": str(args_str)}
                                else:
                                    func = getattr(raw, "function", None)
                                    if func:
                                        tool_name = getattr(func, "name", "unknown")
                                        args_val = getattr(func, "arguments", None)
                                        if args_val:
                                            try:
                                                tool_args = (
                                                    json.loads(args_val)
                                                    if isinstance(args_val, str)
                                                    else args_val
                                                )
                                            except Exception:
                                                tool_args = {"raw": str(args_val)}
                                    else:
                                        name_val = getattr(raw, "name", None)
                                        if name_val:
                                            tool_name = name_val
                                            args_val = getattr(raw, "arguments", None)
                                            if args_val:
                                                try:
                                                    tool_args = (
                                                        json.loads(args_val)
                                                        if isinstance(args_val, str)
                                                        else args_val
                                                    )
                                                except Exception:
                                                    tool_args = {"raw": str(args_val)}

                            # Fallback to direct item attributes
                            if tool_name == "unknown":
                                if hasattr(item, "name") and item.name:
                                    tool_name = item.name
                                elif hasattr(item, "call") and item.call:
                                    call = item.call
                                    if hasattr(call, "function") and call.function:
                                        if hasattr(call.function, "name"):
                                            tool_name = call.function.name
                                        if hasattr(call.function, "arguments"):
                                            try:
                                                tool_args = (
                                                    json.loads(call.function.arguments)
                                                    if isinstance(
                                                        call.function.arguments, str
                                                    )
                                                    else call.function.arguments
                                                )
                                            except Exception:
                                                tool_args = {
                                                    "raw": str(call.function.arguments)
                                                }
                                    elif hasattr(call, "name"):
                                        tool_name = call.name
                                        if hasattr(call, "arguments"):
                                            try:
                                                tool_args = (
                                                    json.loads(call.arguments)
                                                    if isinstance(call.arguments, str)
                                                    else call.arguments
                                                )
                                            except Exception:
                                                tool_args = {"raw": str(call.arguments)}

                            logger.info(
                                f"[AsyncLayeredAgent] Tool call: {tool_name}, "
                                f"args keys: {list(tool_args.keys()) if isinstance(tool_args, dict) else 'not dict'}"
                            )

                            current_tool_call = {
                                "name": tool_name,
                                "args": tool_args,
                            }

                            event_data = {
                                "type": "tool_call",
                                "tool_name": tool_name,
                                "tool_args": tool_args,
                            }
                            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                        elif item_type == "tool_call_output_item":
                            # Tool call result
                            output = getattr(item, "output", "")

                            # Get tool name from current_tool_call or try to extract from item
                            tool_name = (
                                current_tool_call["name"]
                                if current_tool_call
                                else "unknown"
                            )

                            raw_item = getattr(item, "raw_item", None)
                            if tool_name == "unknown" and raw_item:
                                name_val = getattr(raw_item, "name", None)
                                if name_val:
                                    tool_name = name_val

                            logger.info(
                                f"[AsyncLayeredAgent] Tool result for {tool_name}: "
                                f"{str(output)[:100] if output else 'empty'}..."
                            )

                            event_data = {
                                "type": "tool_result",
                                "tool_name": tool_name,
                                "result": output,
                            }
                            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                            current_tool_call = None

                        elif item_type == "message_output_item":
                            content = ""
                            raw_item = getattr(item, "raw_item", None)
                            if raw_item:
                                raw_content = getattr(raw_item, "content", None)
                                if raw_content:
                                    for c in raw_content:
                                        text_val = getattr(c, "text", None)
                                        if text_val:
                                            content += text_val

                            if content:
                                event_data = {
                                    "type": "message",
                                    "content": content,
                                }
                                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            finally:
                # 清理活跃运行实例
                with _async_active_runs_lock:
                    _async_active_runs.pop(session_id, None)

            final_output = (
                result.final_output if hasattr(result, "final_output") else ""
            )
            final_success = True
            event_data = {
                "type": "done",
                "content": final_output,
                "success": True,
            }
            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception(f"[AsyncLayeredAgent] Error: {e}")
            final_output = str(e)
            final_success = False
            event_data = {
                "type": "error",
                "message": str(e),
            }
            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        finally:
            if request.device_id and final_output:
                device_manager = DeviceManager.get_instance()
                serialno = device_manager.get_serial_by_device_id(request.device_id)
                if serialno:
                    end_time = datetime.now()
                    record = ConversationRecord(
                        task_text=request.message,
                        final_message=final_output,
                        success=final_success,
                        steps=0,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=int((end_time - start_time).total_seconds() * 1000),
                        source="async-layered",
                        source_detail=request.session_id or "",
                        error_message=None if final_success else final_output,
                    )
                    history_manager.add_record(serialno, record)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/async-layered-agent/abort")
def async_abort_session(request: AbortSessionRequest) -> dict[str, Any]:
    """Abort a running async layered agent session.

    Uses the OpenAI agents SDK's native cancel() method to stop execution.

    Args:
        request: Abort request containing session_id

    Returns:
        dict: Success status and message
    """
    session_id = request.session_id

    with _async_active_runs_lock:
        if session_id in _async_active_runs:
            result = _async_active_runs[session_id]
            result.cancel(mode="immediate")
            logger.info(f"[AsyncLayeredAgent] Aborted session: {session_id}")
            return {
                "success": True,
                "message": f"Session {session_id} abort signal sent",
            }
        else:
            logger.warning(
                f"[AsyncLayeredAgent] No active run found for session: {session_id}"
            )
            return {
                "success": False,
                "message": f"No active run found for session {session_id}",
            }


@router.post("/api/async-layered-agent/reset")
def async_reset_session(request: ResetSessionRequest) -> dict[str, Any]:
    """Reset/clear a session to forget conversation history.

    This should be called when the user clicks "reset" button
    or refreshes the page.

    Clears all agents for the session and deletes the session.

    Args:
        request: Reset request containing session_id

    Returns:
        dict: Success status and message
    """
    session_id = request.session_id

    if session_id in _async_sessions:
        # 清理所有 agents
        agents = _async_sessions[session_id]["agents"]
        for agent in agents.values():
            agent.reset()  # 重置 agent 状态

        # 删除整个 session
        del _async_sessions[session_id]
        logger.info(f"[AsyncLayeredAgent] Reset session: {session_id}")
        return {
            "success": True,
            "message": f"Session {session_id} reset",
        }

    return {
        "success": True,
        "message": f"Session {session_id} not found (already empty)",
    }
