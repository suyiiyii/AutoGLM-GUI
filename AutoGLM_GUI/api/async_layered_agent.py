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
