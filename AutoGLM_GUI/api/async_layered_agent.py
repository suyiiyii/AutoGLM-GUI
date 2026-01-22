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
