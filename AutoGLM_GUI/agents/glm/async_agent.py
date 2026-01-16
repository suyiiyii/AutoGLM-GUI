"""AsyncGLMAgent - 异步 GLM Agent 实现，支持原生流式输出和立即取消。"""

import asyncio
import json
import traceback
from typing import Any, AsyncIterator, Callable

from openai import AsyncOpenAI

from AutoGLM_GUI.actions import ActionHandler, ActionResult
from AutoGLM_GUI.config import AgentConfig, ModelConfig, StepResult
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.prompt_config import get_messages, get_system_prompt

from .message_builder import MessageBuilder
from .parser import GLMParser


class AsyncGLMAgent:
    """异步 GLM Agent 实现。

    核心特性:
    - 使用 AsyncOpenAI 进行异步 LLM 调用
    - 原生支持流式输出 (async for)
    - 支持立即取消 (asyncio.CancelledError)
    - 使用 asyncio.to_thread 包装同步的设备操作

    与 GLMAgent 的区别:
    - stream() 方法返回 AsyncIterator，不需要 worker 线程
    - cancel() 可以立即中断 HTTP 请求
    - 不需要 monkey-patch thinking_callback
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

        # 使用 AsyncOpenAI
        self.openai_client = AsyncOpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            timeout=120,
        )
        self.parser = GLMParser()

        self.device = device
        self.action_handler = ActionHandler(
            device=self.device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        # 取消机制
        self._cancel_event = asyncio.Event()

        # 初始化 system prompt（Agent 一创建就有"人格"）
        system_prompt = self.agent_config.system_prompt
        if system_prompt is None:
            system_prompt = get_system_prompt(self.agent_config.lang)

        # 保存初始 system message 用于 reset()
        self._initial_system_message = MessageBuilder.create_system_message(
            system_prompt
        )

        # 状态
        self._context: list[dict[str, Any]] = [self._initial_system_message]
        self._step_count = 0
        self._is_running = False

    async def stream(self, task: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行任务，支持取消。

        Args:
            task: 任务描述

        Yields:
            dict[str, Any]: 事件字典，格式为 {"type": str, "data": dict}

        事件类型:
        - "thinking": {"chunk": str}
        - "step": {"step": int, "thinking": str, "action": dict, ...}
        - "done": {"message": str, "steps": int, "success": bool}
        - "cancelled": {"message": str}
        - "error": {"message": str}
        """
        self._is_running = True
        self._cancel_event.clear()

        try:
            # ===== 初始化阶段：添加首次用户输入 =====
            try:
                screenshot = await asyncio.to_thread(self.device.get_screenshot)
                current_app = await asyncio.to_thread(self.device.get_current_app)
            except Exception as e:
                logger.error(f"Failed to get device info during initialization: {e}")
                yield {
                    "type": "error",
                    "data": {"message": f"Device error: {e}"},
                }
                yield {
                    "type": "done",
                    "data": {
                        "message": f"Device error: {e}",
                        "steps": 0,
                        "success": False,
                    },
                }
                return

            screen_info = MessageBuilder.build_screen_info(current_app)
            initial_message = f"{task}\n\n** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=initial_message, image_base64=screenshot.base64_data
                )
            )

            # ===== 执行阶段：循环执行步骤 =====
            while self._step_count < self.agent_config.max_steps and self._is_running:
                # 检查取消
                if self._cancel_event.is_set():
                    raise asyncio.CancelledError()

                async for event in self._execute_step_async():
                    yield event

                    # 检查是否完成
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

            # 达到最大步数
            yield {
                "type": "done",
                "data": {
                    "message": "Max steps reached",
                    "steps": self._step_count,
                    "success": False,
                },
            }

        except asyncio.CancelledError:
            yield {
                "type": "cancelled",
                "data": {"message": "Task cancelled by user"},
            }
            raise

        finally:
            self._is_running = False

    async def _execute_step_async(self) -> AsyncIterator[dict[str, Any]]:
        """执行单步，支持流式输出和取消。

        注意：不再需要 user_prompt 参数，因为：
        - 首次用户输入已在 stream() 的初始化阶段添加
        - 此方法只负责执行步骤：获取屏幕 → 调用 LLM → 执行动作

        Yields:
            dict[str, Any]: 事件字典
        """
        self._step_count += 1

        # 1. 获取当前屏幕状态（使用线程池）
        try:
            screenshot = await asyncio.to_thread(self.device.get_screenshot)
            current_app = await asyncio.to_thread(self.device.get_current_app)
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            yield {
                "type": "error",
                "data": {"message": f"Device error: {e}"},
            }
            yield {
                "type": "step",
                "data": {
                    "step": self._step_count,
                    "thinking": "",
                    "action": None,
                    "success": False,
                    "finished": True,
                    "message": f"Device error: {e}",
                },
            }
            return

        # 2. 构建消息（统一格式：只有屏幕信息）
        screen_info = MessageBuilder.build_screen_info(current_app)
        text_content = f"** Screen Info **\n\n{screen_info}"

        self._context.append(
            MessageBuilder.create_user_message(
                text=text_content, image_base64=screenshot.base64_data
            )
        )

        # 3. 流式调用 OpenAI（真正的异步，可取消）
        try:
            if self.agent_config.verbose:
                msgs = get_messages(self.agent_config.lang)
                logger.debug(f"💭 {msgs['thinking']}:")

            thinking_parts = []
            raw_content = ""

            async for chunk_data in self._stream_openai(self._context):
                # 检查取消
                if self._cancel_event.is_set():
                    raise asyncio.CancelledError()

                if chunk_data["type"] == "thinking":
                    thinking_parts.append(chunk_data["content"])

                    # Yield thinking event
                    yield {
                        "type": "thinking",
                        "data": {"chunk": chunk_data["content"]},
                    }

                    # Verbose output
                    if self.agent_config.verbose:
                        logger.debug(chunk_data["content"])

                elif chunk_data["type"] == "raw":
                    raw_content += chunk_data["content"]

            thinking = "".join(thinking_parts)

        except asyncio.CancelledError:
            logger.info(f"Step {self._step_count} cancelled during LLM call")
            raise

        except Exception as e:
            logger.error(f"LLM error: {e}")
            if self.agent_config.verbose:
                logger.debug(traceback.format_exc())

            yield {
                "type": "error",
                "data": {"message": f"Model error: {e}"},
            }
            yield {
                "type": "step",
                "data": {
                    "step": self._step_count,
                    "thinking": "",
                    "action": None,
                    "success": False,
                    "finished": True,
                    "message": f"Model error: {e}",
                },
            }
            return

        # 4. 解析 action
        _, action_str = self._parse_raw_response(raw_content)

        try:
            action = self.parser.parse(action_str)
        except ValueError as e:
            if self.agent_config.verbose:
                logger.warning(f"Failed to parse action: {e}, treating as finish")
            action = {"_metadata": "finish", "message": action_str}

        if self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            logger.debug(f"🎯 {msgs['action']}:")
            logger.debug(json.dumps(action, ensure_ascii=False, indent=2))

        # 5. 执行 action（使用线程池）
        try:
            result = await asyncio.to_thread(
                self.action_handler.execute, action, screenshot.width, screenshot.height
            )
        except Exception as e:
            logger.error(f"Action execution error: {e}")
            if self.agent_config.verbose:
                logger.debug(traceback.format_exc())
            result = ActionResult(success=False, should_finish=True, message=str(e))

        # 6. 更新上下文
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{thinking}</think><answer>{action_str}</answer>"
            )
        )

        # 7. 检查是否完成
        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            logger.debug(
                f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )

        # 8. 返回步骤结果
        yield {
            "type": "step",
            "data": {
                "step": self._step_count,
                "thinking": thinking,
                "action": action,
                "success": result.success,
                "finished": finished,
                "message": result.message or action.get("message"),
            },
        }

    async def _stream_openai(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[dict[str, str]]:
        """流式调用 OpenAI，yield thinking chunks。

        Args:
            messages: 消息列表

        Yields:
            dict[str, str]: {"type": "thinking" | "raw", "content": str}

        Raises:
            asyncio.CancelledError: 任务被取消
        """
        stream = await self.openai_client.chat.completions.create(
            messages=messages,  # type: ignore[arg-type]
            model=self.model_config.model_name,
            max_tokens=self.model_config.max_tokens,
            temperature=self.model_config.temperature,
            top_p=self.model_config.top_p,
            frequency_penalty=self.model_config.frequency_penalty,
            extra_body=self.model_config.extra_body,
            stream=True,
        )

        buffer = ""
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False

        try:
            async for chunk in stream:
                # 检查取消
                if self._cancel_event.is_set():
                    await stream.close()  # 关键：关闭 HTTP 连接
                    raise asyncio.CancelledError()

                if len(chunk.choices) == 0:
                    continue

                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    yield {"type": "raw", "content": content}

                    if in_action_phase:
                        continue

                    buffer += content

                    # 检查是否到达 action 标记
                    marker_found = False
                    for marker in action_markers:
                        if marker in buffer:
                            thinking_part = buffer.split(marker, 1)[0]
                            yield {"type": "thinking", "content": thinking_part}
                            in_action_phase = True
                            marker_found = True
                            break

                    if marker_found:
                        continue

                    # 检查是否是潜在的 marker 前缀
                    is_potential_marker = False
                    for marker in action_markers:
                        for i in range(1, len(marker)):
                            if buffer.endswith(marker[:i]):
                                is_potential_marker = True
                                break
                        if is_potential_marker:
                            break

                    if not is_potential_marker and len(buffer) > 0:
                        yield {"type": "thinking", "content": buffer}
                        buffer = ""

        finally:
            await stream.close()  # 确保资源释放

    def _parse_raw_response(self, content: str) -> tuple[str, str]:
        """解析原始响应，提取 thinking 和 action。

        Args:
            content: 原始响应内容

        Returns:
            tuple[str, str]: (thinking, action)
        """
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = parts[0].strip()
            action = "finish(message=" + parts[1]
            return thinking, action

        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = parts[0].strip()
            action = "do(action=" + parts[1]
            return thinking, action

        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = parts[0].replace("<think>", "").replace("</think>", "").strip()
            action = parts[1].replace("</answer>", "").strip()
            return thinking, action

        return "", content

    async def cancel(self) -> None:
        """取消当前执行。

        设置取消标志，中断正在进行的 HTTP 请求。
        """
        self._cancel_event.set()
        self._is_running = False
        logger.info("AsyncGLMAgent cancelled by user")

    def reset(self) -> None:
        """重置状态（恢复到初始状态，保留 system message）。"""
        self._context = [self._initial_system_message]
        self._step_count = 0
        self._is_running = False
        self._cancel_event.clear()

    async def run(self, task: str) -> str:
        """运行完整任务（兼容接口）。

        Args:
            task: 任务描述

        Returns:
            str: 最终结果消息
        """
        final_message = ""
        async for event in self.stream(task):
            if event["type"] == "done":
                final_message = event["data"].get("message", "")
        return final_message

    async def step(self, task: str | None = None) -> StepResult:
        """执行单步（兼容接口）。

        Args:
            task: 任务描述（首步必需，后续可选）

        Returns:
            StepResult: 步骤结果
        """
        is_first_execution = len(self._context) == 1  # 只有 system message
        if is_first_execution:
            if not task:
                raise ValueError("Task is required for the first step")

            # 首次执行：需要先添加用户输入
            try:
                screenshot = await asyncio.to_thread(self.device.get_screenshot)
                current_app = await asyncio.to_thread(self.device.get_current_app)
            except Exception as e:
                logger.error(f"Failed to get device info during initialization: {e}")
                raise RuntimeError(f"Device error: {e}") from e

            screen_info = MessageBuilder.build_screen_info(current_app)
            initial_message = f"{task}\n\n** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=initial_message, image_base64=screenshot.base64_data
                )
            )

        # 执行步骤
        result = None
        async for event in self._execute_step_async():
            if event["type"] == "step":
                result = StepResult(
                    thinking=event["data"]["thinking"],
                    action=event["data"]["action"],
                    success=event["data"]["success"],
                    finished=event["data"]["finished"],
                    message=event["data"].get("message"),
                )

        if result is None:
            raise RuntimeError("Step execution did not produce a result")

        return result

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def context(self) -> list[dict[str, Any]]:
        return self._context.copy()

    @property
    def is_running(self) -> bool:
        return self._is_running
