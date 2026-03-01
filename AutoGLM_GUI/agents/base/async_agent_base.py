"""AsyncAgentBase - 异步 Agent 基类，提取 GLM/Gemini 共享逻辑。

子类只需实现:
- _get_default_system_prompt(lang) → 默认 system prompt
- _prepare_initial_context(task, screenshot, current_app) → 构建首条消息
- _execute_step() → 单步执行（LLM 调用 + action 执行）
"""

import asyncio
import copy
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, AsyncIterator, Callable

from openai import AsyncOpenAI

from AutoGLM_GUI.actions import ActionHandler
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder


class AsyncAgentBase(ABC):
    """异步 Agent 基类。

    提供共享的:
    - OpenAI client 初始化
    - ActionHandler 初始化
    - stream() 主循环（截图 → 步骤循环 → 完成/取消）
    - cancel / reset / run / properties
    """

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        device: DeviceProtocol,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config
        self.agent_config = agent_config

        self.openai_client = AsyncOpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            timeout=120,
        )

        self.device = device
        self.action_handler = ActionHandler(
            device=self.device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self._cancel_event = asyncio.Event()

        # System prompt: 优先用配置的，否则用子类默认的
        system_prompt = self.agent_config.system_prompt
        if system_prompt is None:
            system_prompt = self._get_default_system_prompt(self.agent_config.lang)

        self._initial_system_message = MessageBuilder.create_system_message(
            system_prompt
        )

        # State
        self._context: list[dict[str, Any]] = [self._initial_system_message]
        self._step_count = 0
        self._is_running = False

    # ==================== 子类必须实现 ====================

    @abstractmethod
    def _get_default_system_prompt(self, lang: str) -> str:
        """返回默认 system prompt。"""
        ...

    @abstractmethod
    def _prepare_initial_context(
        self, task: str, screenshot_base64: str, current_app: str
    ) -> None:
        """构建首条用户消息并添加到 self._context。"""
        ...

    @abstractmethod
    async def _execute_step(self) -> AsyncGenerator[dict[str, Any], None]:
        """执行单步：获取截图 → 调用 LLM → 执行动作。

        子类必须实现为 async generator（使用 yield）。
        """
        raise NotImplementedError
        yield  # pragma: no cover — make Pyright see this as async generator

    # ==================== 共享逻辑 ====================

    async def stream(self, task: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行任务，支持取消。"""
        self._is_running = True
        self._cancel_event.clear()

        try:
            # 初始化：获取首屏截图
            try:
                screenshot = await asyncio.to_thread(self.device.get_screenshot)
                current_app = await asyncio.to_thread(self.device.get_current_app)
            except Exception as e:
                logger.error(f"Failed to get device info: {e}")
                yield {"type": "error", "data": {"message": f"Device error: {e}"}}
                yield {
                    "type": "done",
                    "data": {
                        "message": f"Device error: {e}",
                        "steps": 0,
                        "success": False,
                    },
                }
                return

            # 子类构建首条消息
            self._prepare_initial_context(task, screenshot.base64_data, current_app)

            # 执行循环
            while self._step_count < self.agent_config.max_steps and self._is_running:
                if self._cancel_event.is_set():
                    raise asyncio.CancelledError()

                async for event in self._execute_step():
                    yield event

                    if event["type"] == "step" and event["data"].get("finished"):
                        yield {
                            "type": "done",
                            "data": {
                                "message": event["data"].get(
                                    "message", "Task completed"
                                ),
                                "steps": self._step_count,
                                "success": event["data"].get("success", True),
                            },
                        }
                        return

            yield {
                "type": "done",
                "data": {
                    "message": "Max steps reached",
                    "steps": self._step_count,
                    "success": False,
                },
            }

        except asyncio.CancelledError:
            yield {"type": "cancelled", "data": {"message": "Task cancelled by user"}}
            raise

        finally:
            self._is_running = False

    async def cancel(self) -> None:
        """取消当前执行。"""
        self._cancel_event.set()
        self._is_running = False
        logger.info(f"{self.__class__.__name__} cancelled by user")

    def reset(self) -> None:
        """重置状态。"""
        self._context = [copy.deepcopy(self._initial_system_message)]
        self._step_count = 0
        self._is_running = False
        self._cancel_event.clear()

    async def run(self, task: str) -> str:
        """运行完整任务（兼容接口）。"""
        final_message = ""
        async for event in self.stream(task):
            if event["type"] == "done":
                final_message = event["data"].get("message", "")
        return final_message

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def context(self) -> list[dict[str, Any]]:
        return self._context.copy()

    @property
    def is_running(self) -> bool:
        return self._is_running
