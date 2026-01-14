from __future__ import annotations

import inspect
from typing import Any, AsyncIterator, Protocol

from AutoGLM_GUI.config import AgentConfig, ModelConfig, StepResult


def is_async_agent(agent: AsyncAgent | BaseAgent) -> bool:
    """Check if an agent implements the AsyncAgent interface.

    Uses runtime inspection to detect async capabilities since static
    type narrowing is not possible with Protocol union types.

    Args:
        agent: Agent instance to check

    Returns:
        True if agent has async stream() method, False otherwise
    """
    stream_method = getattr(agent, "stream", None)
    return stream_method is not None and inspect.isasyncgenfunction(stream_method)


class BaseAgent(Protocol):
    model_config: ModelConfig
    agent_config: AgentConfig

    def run(self, task: str) -> str: ...

    def step(self, task: str | None = None) -> StepResult: ...

    def reset(self) -> None: ...

    def abort(self) -> None: ...

    @property
    def step_count(self) -> int: ...

    @property
    def context(self) -> list[dict[str, Any]]: ...

    @property
    def is_running(self) -> bool: ...


class AsyncAgent(Protocol):
    """异步 Agent 接口，原生支持流式输出和取消。

    核心特性:
    - stream() 方法返回 AsyncIterator[dict]，支持原生 async for
    - cancel() 方法使用 asyncio 取消机制，可立即中断 HTTP 请求
    - 不需要 worker 线程、queue、monkey-patch

    使用示例:
        async for event in agent.stream("打开微信"):
            if event["type"] == "thinking":
                print(event["data"]["chunk"])
            elif event["type"] == "step":
                print(f"Step {event['data']['step']}")
            elif event["type"] == "done":
                break
    """

    model_config: ModelConfig
    agent_config: AgentConfig

    async def run(self, task: str) -> str:
        """运行完整任务，返回最终结果。

        Args:
            task: 任务描述

        Returns:
            str: 最终结果消息
        """
        ...

    async def step(self, task: str | None = None) -> StepResult:
        """执行单步，返回步骤结果。

        Args:
            task: 任务描述（首步必需，后续可选）

        Returns:
            StepResult: 步骤结果
        """
        ...

    async def stream(self, task: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行任务，yield 事件字典。

        这是核心方法，支持:
        - 实时流式输出 (thinking chunks)
        - 立即取消 (通过 asyncio.CancelledError)
        - 不需要额外的线程或队列

        事件类型:
        - "thinking": {"chunk": str} - 思考过程片段
        - "step": {"step": int, "thinking": str, "action": dict, ...} - 步骤完成
        - "done": {"message": str, "steps": int, "success": bool} - 任务完成
        - "cancelled": {"message": str} - 任务取消
        - "error": {"message": str} - 错误

        Args:
            task: 任务描述

        Yields:
            dict[str, Any]: 事件字典，格式为 {"type": str, "data": dict}

        Raises:
            asyncio.CancelledError: 任务被取消
        """
        ...

    async def cancel(self) -> None:
        """取消当前执行（立即中断网络请求）。

        使用 asyncio 的取消机制，会:
        1. 设置内部取消标志
        2. 关闭正在进行的 HTTP 连接
        3. 抛出 asyncio.CancelledError
        """
        ...

    def reset(self) -> None:
        """重置状态（同步方法，只清理内存）。"""
        ...

    @property
    def step_count(self) -> int: ...

    @property
    def context(self) -> list[dict[str, Any]]: ...

    @property
    def is_running(self) -> bool: ...
