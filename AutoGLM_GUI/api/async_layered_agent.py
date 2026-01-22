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
