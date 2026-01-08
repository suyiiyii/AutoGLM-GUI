"""Layered agent API for hierarchical task execution.

This module provides the layered agent API endpoint that uses
a decision model for planning and autoglm-phone for execution.
"""

import asyncio
import json
import threading
from typing import TYPE_CHECKING, Any

from agents import Agent, Runner, SQLiteSession, function_tool

if TYPE_CHECKING:
    from agents.result import RunResultStreaming
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from AutoGLM_GUI.config_manager import config_manager
from AutoGLM_GUI.logger import logger

router = APIRouter()

# ==================== Session 管理 ====================
# 存储每个 session_id 对应的 SQLiteSession（内存模式）
_sessions: dict[str, SQLiteSession] = {}

# ==================== 活跃运行管理 ====================
# 存储每个 session_id 对应的活跃 RunResultStreaming 实例，用于 abort
_active_runs: dict[str, "RunResultStreaming"] = {}
_active_runs_lock = threading.Lock()


def _get_or_create_session(session_id: str) -> SQLiteSession:
    """获取或创建指定 session_id 的内存 session."""
    if session_id not in _sessions:
        # 使用 session_id 作为会话名称创建 session
        _sessions[session_id] = SQLiteSession(session_id)
        logger.info(f"[LayeredAgent] Created new session: {session_id}")
    return _sessions[session_id]


def _clear_session(session_id: str) -> bool:
    """清除指定 session_id 的 session."""
    if session_id in _sessions:
        del _sessions[session_id]
        logger.info(f"[LayeredAgent] Cleared session: {session_id}")
        return True
    return False


def get_planner_model() -> str:
    """获取规划层使用的模型名称."""
    config_manager.load_file_config()
    effective_config = config_manager.get_effective_config()

    model_name = effective_config.decision_model_name

    if not model_name:
        raise ValueError(
            "决策模型未配置。使用分层代理模式需要配置决策模型。\n"
            "请在全局配置中设置决策模型的 Base URL、模型名称和 API Key。"
        )

    logger.info(f"[LayeredAgent] Using decision model: {model_name}")
    return model_name


PLANNER_INSTRUCTIONS = """## 核心目标
你是一个负责操控手机的高级智能中枢。你的任务是将用户的意图转化为**视觉模型（Vision Model）**可以执行的原子操作。

## ⚠️ 极其重要的限制：视觉模型的能力边界 (Must Read)
你的下级（Vision Model）是一个**纯粹的执行者和观察者**。
1. **无"记忆/笔记"功能**：它没有 `Note` 功能，无法为你保存数据。
2. **无"系统级"权限**：它不能复制源代码，不能直接提取文本，不能读取剪贴板。
3. **唯一的输出**：它只能通过**对话**告诉你它看到了什么，或者去**点击/滑动**屏幕。

## 交互策略 (Interaction Strategy)

### 1. 如果你需要"操作手机" (To Act)
下达明确的 UI 动作指令。
- ✅ "点击'设置'图标。"
- ✅ "向下滑动屏幕。"
- ✅ "打开微信。"

### 2. 如果你需要"获取信息" (To Read/Extract)
你必须通过**提问**的方式，让视觉模型在对话中把信息"念"给你听。
- ❌ **错误**: "把验证码保存下来。" (它做不到)
- ❌ **错误**: "使用 Note 功能记录价格。" (它没有这个功能)
- ✅ **正确**: 调用 `chat` 询问："请看屏幕，告诉我现在的订单总金额是多少？"
  - *结果*: 视觉模型会回复 "25.5元"。你需要自己处理这个文本信息。

### 3. 如果用户要求"复制/粘贴"
必须通过模拟手指操作来实现，不能直接操作剪贴板。
- ✅ **正确**: "长按这段文字，等待弹出菜单，然后点击'复制'按钮。"

## 任务拆解原则 (Decomposition Rules)

1. **原子化**: 每次只给一个动作。
2. **可视化**: 指令必须基于屏幕上**看得见**的元素。不要说"点击确认"，如果屏幕上显示的按钮叫"OK"，请说"点击'OK'按钮"。
3. **Fail Fast**: 如果视觉模型回复 `ELEMENT_NOT_FOUND`，不要死循环。询问它："那现在屏幕上有什么？"或者尝试滑动寻找。

## 核心工作流 (The Loop)
1. **Observe (看)**: 调用 `chat` 询问当前状态。
   - "现在屏幕上显示什么？" / "刚才的点击生效了吗？"
2. **Think (想)**:
   - 用户的目标是什么？
   - 我需要让视觉模型**做什么动作**，还是**回答什么问题**？
3. **Act (做)**:
   - **Case A (动作)**: 发送指令 `点击[坐标]...`
   - **Case B (询问)**: 发送问题 `请读取...`

## 内部思维链示例 (Inner Monologue)

**场景 1: 用户让你"把这篇笔记的标题发给我"**
> **Current State**: 笔记详情页。
> **Goal**: 获取标题文本。
> **Constraint**: 视觉模型无法直接提取变量，我必须问它。
> **Strategy**: 问视觉模型标题是什么，它回答后，我再反馈给用户。
> **Next Action**: 提问。
**Output**: `chat(id, "请读取并告诉我屏幕上这篇笔记的标题文字内容是什么？")`

**场景 2: 用户让你"复制链接"**
> **Current State**: 详情页。
> **Goal**: 把链接复制到系统剪贴板。
> **Constraint**: 不能直接 Get Link。必须找"分享"或"复制"按钮。
> **Strategy**: 先点右上角菜单，再找复制链接。
> **Next Action**: 点击菜单。
**Output**: `chat(id, "点击屏幕右上角的'...'（三个点）菜单按钮。")`

## 工具集 (Tools)
1. `list_devices()`
2. `chat(device_id, message)`: 
   - 发送操作指令（如"点击红色按钮"）。
   - 发送查询问题（如"那个验证码是多少？"）。

"""


# ==================== 工具定义 ====================


def _sync_list_devices() -> str:
    """同步实现：获取所有连接的 ADB 设备列表。"""
    from AutoGLM_GUI.api.devices import _build_device_response_with_agent
    from AutoGLM_GUI.device_manager import DeviceManager
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    logger.info("[LayeredAgent] list_devices tool called")

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
async def list_devices() -> str:
    """
    获取所有连接的 ADB 设备列表。

    返回设备信息包括:
    - id: 设备标识符，用于 chat 工具调用
    - model: 设备型号
    - status: 连接状态
    - connection_type: 连接类型 (usb/wifi/remote)

    Returns:
        JSON 格式的设备列表
    """
    return await asyncio.to_thread(_sync_list_devices)


def _sync_chat(device_id: str, message: str) -> str:
    """同步实现：向指定设备的 Phone Agent 发送子任务指令。"""
    from AutoGLM_GUI.exceptions import DeviceBusyError
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
    from AutoGLM_GUI.prompts import MCP_SYSTEM_PROMPT_ZH

    MCP_MAX_STEPS = 5

    logger.info(
        f"[LayeredAgent] chat tool called: device_id={device_id}, message={message}"
    )

    manager = PhoneAgentManager.get_instance()

    try:
        # use_agent 现在会自动初始化 agent（auto_initialize=True）
        with manager.use_agent(device_id, timeout=None) as agent:
            # 临时覆盖配置
            original_max_steps = agent.agent_config.max_steps
            original_system_prompt = agent.agent_config.system_prompt

            agent.agent_config.max_steps = MCP_MAX_STEPS
            agent.agent_config.system_prompt = MCP_SYSTEM_PROMPT_ZH

            try:
                # 重置 agent 确保干净状态
                agent.reset()

                result = agent.run(message)
                steps = agent.step_count

                # 检查是否达到步数限制
                if steps >= MCP_MAX_STEPS and result == "Max steps reached":
                    context_json = json.dumps(
                        agent.context, ensure_ascii=False, indent=2
                    )
                    return json.dumps(
                        {
                            "result": f"⚠️ 已达到最大步数限制（{MCP_MAX_STEPS}步）。视觉模型可能遇到了困难，任务未完成。\n\n执行历史:\n{context_json}\n\n建议: 请重新规划任务或将其拆分为更小的子任务。",
                            "steps": MCP_MAX_STEPS,
                            "success": False,
                        },
                        ensure_ascii=False,
                    )

                return json.dumps(
                    {
                        "result": result,
                        "steps": steps,
                        "success": True,
                    },
                    ensure_ascii=False,
                )

            finally:
                # 恢复原始配置
                agent.agent_config.max_steps = original_max_steps
                agent.agent_config.system_prompt = original_system_prompt

    except DeviceBusyError:
        return json.dumps(
            {
                "result": f"设备 {device_id} 正忙，请稍后再试。",
                "steps": 0,
                "success": False,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"[LayeredAgent] chat tool error: {e}")
        return json.dumps(
            {
                "result": str(e),
                "steps": 0,
                "success": False,
            },
            ensure_ascii=False,
        )


@function_tool
async def chat(device_id: str, message: str) -> str:
    """
    向指定设备的 Phone Agent 发送子任务指令。

    Phone Agent 是一个视觉模型，能够看到手机屏幕并执行操作。
    每次调用会执行一个原子化的子任务（最多 5 步操作）。

    Args:
        device_id: 设备标识符，从 list_devices 获取
        message: 子任务指令，例如 "打开微信"、"点击搜索按钮"

    Returns:
        JSON 格式的执行结果，包含:
        - result: 执行结果描述
        - steps: 执行的步数
        - success: 是否成功
    """
    return await asyncio.to_thread(_sync_chat, device_id, message)


# ==================== Agent 初始化 ====================


def _setup_openai_client() -> AsyncOpenAI:
    """设置 OpenAI 客户端，使用决策模型配置"""
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
    planner_model = get_planner_model()  # 这里会再次检查 model_name

    logger.info("[LayeredAgent] Decision model config:")
    logger.info(f"  - Base URL: {decision_base_url}")
    logger.info(f"  - Model: {planner_model}")
    logger.info(f"  - API Key: {'***' if decision_api_key else 'None'}")

    return AsyncOpenAI(
        base_url=decision_base_url,
        api_key=decision_api_key or "EMPTY",  # 某些本地模型需要非空字符串
    )


def _create_planner_agent(client: AsyncOpenAI) -> Agent[Any]:
    """创建规划 Agent，使用 Chat Completions API"""
    planner_model = get_planner_model()
    model = OpenAIChatCompletionsModel(
        model=planner_model,
        openai_client=client,
    )

    return Agent(
        name="Planner",
        instructions=PLANNER_INSTRUCTIONS,
        model=model,
        tools=[list_devices, chat],
    )


# Global agent instance (lazy initialized)
_client: AsyncOpenAI | None = None
_agent: Agent[Any] | None = None
_cached_config_hash: str | None = None


def _compute_config_hash() -> str:
    import hashlib

    config = config_manager.get_effective_config()
    config_str = config.model_dump_json()
    return hashlib.md5(config_str.encode()).hexdigest()


def _ensure_agent() -> Agent[Any]:
    global _client, _agent, _cached_config_hash

    current_hash = _compute_config_hash()

    if _agent is None or _cached_config_hash != current_hash:
        if _agent is not None and _cached_config_hash != current_hash:
            logger.info(
                f"[LayeredAgent] Config changed (hash: {_cached_config_hash} -> {current_hash}), reloading agent..."
            )

        _client = _setup_openai_client()
        _agent = _create_planner_agent(_client)
        _cached_config_hash = current_hash
        logger.info(
            f"[LayeredAgent] Agent initialized/reloaded with config hash: {current_hash}"
        )

    return _agent


# ==================== API 路由 ====================


class LayeredAgentRequest(BaseModel):
    """Request for layered agent chat."""

    message: str
    device_id: str | None = None
    session_id: str | None = None  # 用于保持对话上下文，前端可传入 deviceId


@router.post("/api/layered-agent/chat")
async def layered_agent_chat(request: LayeredAgentRequest):
    """
    Layered agent chat API with streaming execution steps.

    Uses a decision model for planning and autoglm-phone for execution.

    Returns SSE stream with events:
    - tool_call: Agent is calling a tool (with tool_name and tool_args)
    - tool_result: Tool execution result
    - message: Intermediate message from agent
    - done: Final response
    - error: Error occurred
    """
    from datetime import datetime

    from agents.stream_events import (
        RawResponsesStreamEvent,
        RunItemStreamEvent,
    )

    from AutoGLM_GUI.history_manager import history_manager
    from AutoGLM_GUI.models.history import ConversationRecord

    async def event_generator():
        start_time = datetime.now()
        final_output = ""
        final_success = False

        try:
            agent = _ensure_agent()

            session_id = request.session_id or request.device_id or "default"
            session = _get_or_create_session(session_id)

            # Run the agent with streaming and session for memory
            result = Runner.run_streamed(
                agent,
                request.message,
                max_turns=50,
                session=session,
            )

            # 保存活跃运行实例，用于 abort
            with _active_runs_lock:
                _active_runs[session_id] = result

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

                                # Handle dict format (sometimes returned as dict)
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
                                f"[LayeredAgent] Tool call: {tool_name}, args keys: {list(tool_args.keys()) if isinstance(tool_args, dict) else 'not dict'}"
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
                                f"[LayeredAgent] Tool result for {tool_name}: {str(output)[:100] if output else 'empty'}..."
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
                with _active_runs_lock:
                    _active_runs.pop(session_id, None)

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
            logger.exception(f"[LayeredAgent] Error: {e}")
            final_output = str(e)
            final_success = False
            event_data = {
                "type": "error",
                "message": str(e),
            }
            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        finally:
            if request.device_id and final_output:
                from AutoGLM_GUI.device_manager import DeviceManager

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
                        source="layered",
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


class AbortSessionRequest(BaseModel):
    """Request for aborting a running session."""

    session_id: str


@router.post("/api/layered-agent/abort")
def abort_session(request: AbortSessionRequest):
    """
    Abort a running layered agent session.

    Uses the OpenAI agents SDK's native cancel() method to stop execution.
    """
    session_id = request.session_id

    with _active_runs_lock:
        if session_id in _active_runs:
            result = _active_runs[session_id]
            result.cancel(mode="immediate")
            logger.info(f"[LayeredAgent] Aborted session: {session_id}")
            return {
                "success": True,
                "message": f"Session {session_id} abort signal sent",
            }
        else:
            logger.warning(
                f"[LayeredAgent] No active run found for session: {session_id}"
            )
            return {
                "success": False,
                "message": f"No active run found for session {session_id}",
            }


class ResetSessionRequest(BaseModel):
    """Request for resetting a session."""

    session_id: str


@router.post("/api/layered-agent/reset")
def reset_session(request: ResetSessionRequest):
    """
    Reset/clear a session to forget conversation history.

    This should be called when the user clicks "reset" button
    or refreshes the page.
    """
    cleared = _clear_session(request.session_id)
    return {
        "success": True,
        "message": f"Session {request.session_id} {'cleared' if cleared else 'not found (already empty)'}",
    }
