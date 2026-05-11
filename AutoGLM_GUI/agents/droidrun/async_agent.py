"""DroidRunAgent - DroidRun 框架集成适配器。

将 DroidRun 的 DroidAgent 包装为 AutoGLM-GUI 的 AsyncAgent 接口。
DroidRun 自行管理 ADB 连接，不依赖 AutoGLM-GUI 的 DeviceProtocol 层。

前置条件：设备上需安装 DroidRun Portal APK。
安装方法：droidrun setup --device <serial>
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.logger import logger


class DroidRunAgent:
    """DroidRun Agent 适配器，实现 AsyncAgent Protocol。

    将 DroidRun 的事件流转换为 AutoGLM-GUI 的标准事件格式。
    DroidRun 独立管理 ADB 连接，不与 AutoGLM-GUI 的 DeviceProtocol 共享。
    """

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        device: Any,
        takeover_callback: Any = None,  # noqa: ARG002
        confirmation_callback: Any = None,  # noqa: ARG002
    ) -> None:
        self.model_config = model_config
        self.agent_config = agent_config
        self._device = device
        self._step_count = 0
        self._cancel_event = asyncio.Event()

    async def stream(self, task: str) -> AsyncGenerator[dict[str, Any], None]:
        """流式执行任务，将 DroidRun 事件转换为 AutoGLM-GUI 格式。"""
        self._step_count = 0
        self._cancel_event.clear()

        # Portal APK 提示
        yield {
            "type": "thinking",
            "data": {
                "chunk": (
                    "[DroidRun 模式] 注意：此模式需要在 Android 设备上安装 DroidRun Portal APK。\n"
                    "如未安装，请先运行：droidrun setup --device <serial>"
                )
            },
        }

        # 延迟导入，未安装时给出友好提示
        try:
            from droidrun.agent.codeact.events import (  # pyright: ignore[reportMissingImports]
                CodeActResponseEvent,
            )
            from droidrun.agent.droid.droid_agent import (  # pyright: ignore[reportMissingImports]
                DroidAgent,
            )
            from droidrun.agent.droid import (  # pyright: ignore[reportMissingImports]
                events as droid_events,
            )
            from droidrun.agent.utils.llm_picker import (  # pyright: ignore[reportMissingImports]
                load_llm,
            )
            from droidrun.config_manager.config_manager import (  # pyright: ignore[reportMissingImports,reportAttributeAccessIssue]
                DeviceConfig,
                DroidConfig,  # pyright: ignore[reportAttributeAccessIssue]
            )
        except ImportError as e:
            yield {
                "type": "error",
                "data": {
                    "message": (
                        f"droidrun 未安装，请运行：uv pip install droidrun\n错误：{e}"
                    )
                },
            }
            return

        # droidrun 0.4.x: CodeActResultEvent; 0.5.x: FastAgentResultEvent
        codeact_result_event_cls = getattr(droid_events, "CodeActResultEvent", None)
        fast_agent_result_event_cls = getattr(
            droid_events, "FastAgentResultEvent", None
        )
        ExecutorResultEvent = droid_events.ExecutorResultEvent
        FinalizeEvent = droid_events.FinalizeEvent
        ManagerPlanEvent = droid_events.ManagerPlanEvent
        ResultEvent = droid_events.ResultEvent

        # 利用闭包将已导入的事件类型内联到转换函数中
        def convert_event(event: Any) -> dict[str, Any] | None:
            """将 DroidRun 事件转换为 AutoGLM-GUI 事件格式。"""
            # ── CodeAct 内部逐步事件（reasoning=False 模式）──
            if isinstance(event, CodeActResponseEvent):
                if event.thought:
                    return {"type": "thinking", "data": {"chunk": event.thought}}
                return None

            is_codeact_result = (
                codeact_result_event_cls is not None
                and isinstance(event, codeact_result_event_cls)
            ) or (
                fast_agent_result_event_cls is not None
                and isinstance(event, fast_agent_result_event_cls)
            )
            if is_codeact_result:
                summary = getattr(event, "summary", None) or getattr(
                    event, "reason", ""
                )
                action = getattr(event, "action", None) or getattr(
                    event, "instruction", "code execution"
                )
                success = getattr(event, "success", getattr(event, "outcome", True))
                self._step_count += 1
                return {
                    "type": "step",
                    "data": {
                        "step": self._step_count,
                        "thinking": summary,
                        "action": {
                            "_metadata": "DroidRun",
                            "description": str(action),
                        },
                        "success": success,
                        "finished": False,
                        "message": None,
                    },
                }

            # ── Manager / Executor 事件（reasoning=True 模式）──
            if isinstance(event, ManagerPlanEvent):
                text = event.current_subgoal
                if event.thought:
                    text = f"{event.thought}\n[子目标] {event.current_subgoal}"
                return {"type": "thinking", "data": {"chunk": text}}

            if isinstance(event, ExecutorResultEvent):
                self._step_count += 1
                return {
                    "type": "step",
                    "data": {
                        "step": self._step_count,
                        "thinking": event.summary or "",
                        "action": {
                            "_metadata": "DroidRun",
                            "description": str(event.action),
                        },
                        "success": event.outcome,
                        "finished": False,
                        "message": event.error if not event.outcome else None,
                    },
                }

            # ── 最终结果事件 ──
            if isinstance(event, ResultEvent):
                return {
                    "type": "done",
                    "data": {
                        "success": event.success,
                        "message": event.reason,
                        "steps": event.steps or self._step_count,
                    },
                }

            if isinstance(event, FinalizeEvent):
                return {
                    "type": "thinking",
                    "data": {"chunk": f"[完成中] {event.reason}"},
                }

            return None

        # 构建 DroidConfig（只需设备配置，LLM 直接传入）
        config = DroidConfig()
        config.device = DeviceConfig(serial=self._device.device_id)
        config.telemetry.enabled = False
        config.agent.max_steps = (
            self.agent_config.max_steps
            if self.agent_config.max_steps is not None
            else 100000
        )
        config.agent.reasoning = False

        # 加载 LLM（OpenAI 兼容接口）
        try:
            llm = load_llm(
                "OpenAILike",
                model=self.model_config.model_name,
                api_base=self.model_config.base_url,
                api_key=self.model_config.api_key or "no-key",
            )
        except Exception as e:
            logger.error(f"LLM 加载失败: {e}")
            yield {"type": "error", "data": {"message": f"LLM 加载失败：{e}"}}
            return

        # 创建 DroidAgent（直接传入 LLM 实例，绕过 profile 验证）
        try:
            agent = DroidAgent(goal=task, llms=llm, config=config)
        except Exception as e:
            logger.error(f"DroidAgent 初始化失败: {e}")
            yield {"type": "error", "data": {"message": f"DroidAgent 初始化失败：{e}"}}
            return

        # 执行并转换事件流
        # DroidAgent.run() 实际返回 WorkflowHandler，但类型标注为 Awaitable[ResultEvent]
        handler: Any = agent.run()
        try:
            async for event in handler.stream_events():
                if self._cancel_event.is_set():
                    handler.cancel()
                    yield {"type": "cancelled", "data": {"message": "任务已取消"}}
                    return

                converted = convert_event(event)
                if converted is not None:
                    yield converted
                    if converted["type"] == "done":
                        return
        except Exception as e:
            logger.error(f"DroidRun 执行错误: {e}")
            yield {"type": "error", "data": {"message": f"执行错误：{e}"}}

    async def cancel(self) -> None:
        """取消当前执行。"""
        self._cancel_event.set()

    async def run(self, task: str) -> str:
        """运行完整任务，返回最终结果消息。"""
        result = ""
        async for event in self.stream(task):
            if event.get("type") == "done":
                result = event.get("data", {}).get("message", "")
        return result

    def reset(self) -> None:
        """重置状态。"""
        self._cancel_event.clear()
        self._step_count = 0

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def context(self) -> list[dict[str, Any]]:
        return []

    @property
    def is_running(self) -> bool:
        return False
