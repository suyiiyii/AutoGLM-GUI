"""AsyncQwenAgent - 异步 Qwen Agent，使用流式文本解析。"""

import os
import base64
import asyncio
import json
import traceback
from collections.abc import AsyncGenerator
from typing import Any
from collections.abc import Callable

from io import BytesIO
from datetime import datetime
from PIL import Image, ImageDraw

from AutoGLM_GUI.agents.base import AsyncAgentBase
from AutoGLM_GUI.agents.protocols import AsyncAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder
from AutoGLM_GUI.prompt_config import get_messages
from AutoGLM_GUI.trace import trace_span


from .parser import QwenParser
from . import SYSTEM_PROMPT_EN, SYSTEM_PROMPT_ZH


def get_system_prompt(lang: str = "cn") -> str:
    if lang == "en":
        return SYSTEM_PROMPT_EN
    return SYSTEM_PROMPT_ZH


def _count_image_parts(messages: list[dict[str, Any]]) -> int:
    count = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            count += sum(
                1
                for part in content
                if isinstance(part, dict) and part.get("type") == "image_url"
            )
    return count


class AsyncQwenAgent(AsyncAgentBase, AsyncAgent):
    """异步 Qwen Agent，通过流式文本 + 自定义格式解析执行操作。"""

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        device: DeviceProtocol,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.parser = QwenParser()
        super().__init__(
            model_config=model_config,
            agent_config=agent_config,
            device=device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )
        # Task text is stashed here and merged into the first per-step user
        # message (together with that step's screenshot), matching the
        # official Open-AutoGLM layout.
        self._pending_task: str | None = None
        self._pending_reference_images: list[dict[str, str]] = []

    def _get_default_system_prompt(self, lang: str) -> str:
        return get_system_prompt(lang)

    def _prepare_initial_context(
        self,
        task: str,
        screenshot_base64: str,
        current_app: str,
        reference_images: list[dict[str, str]] | None = None,
    ) -> None:
        # Do not add a screenshot here: the first per-step screenshot is the
        # current one and it is attached in _execute_step(). This keeps the
        # invariant that every LLM request carries the current screen first.
        self._pending_task = task
        self._pending_reference_images = (reference_images or []).copy()

    def _draw_tap_debug(
        self,
        screenshot_base64: str,
        x: int,
        y: int,
        action_name: str,
        step: int,
    ) -> str | None:
        """在截图上绘制红色标记点，保存原图和调试图并返回调试图路径。"""
        try:
            img_data = base64.b64decode(screenshot_base64)
            img = Image.open(BytesIO(img_data))

            # 保存 debug 目录
            debug_dir = os.path.join(os.getcwd(), "logs/debug_taps")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 保存原图
            original_filename = f"{timestamp}_step_{step}_original.png"
            original_path = os.path.join(debug_dir, original_filename)
            img.save(original_path)

            # 绘制红色实心圆 + 十字线
            draw = ImageDraw.Draw(img)
            r = 30
            draw.ellipse(
                [x - r, y - r, x + r, y + r], fill="red", outline="darkred", width=2
            )
            draw.line([(x - r - 5, y), (x + r + 5, y)], fill="yellow", width=2)
            draw.line([(x, y - r - 5), (x, y + r + 5)], fill="yellow", width=2)

            # 保存标记图
            debug_filename = f"{timestamp}_step_{step}_{action_name}.png"
            debug_path = os.path.join(debug_dir, debug_filename)
            img.save(debug_path)
            return debug_path
        except Exception as e:
            logger.warning(f"Failed to draw tap debug: {e}")
            return None

    async def _execute_step(self) -> AsyncGenerator[dict[str, Any], None]:
        """执行单步：获取截图 → 流式调用 LLM → 解析文本 → 执行动作。"""
        self._step_count += 1

        # 1. 获取当前屏幕状态
        try:
            with trace_span(
                "step.capture_screenshot",
                attrs={"step": self._step_count, "agent_type": self.__class__.__name__},
            ):
                screenshot = await asyncio.to_thread(self.device.get_screenshot)
            with trace_span(
                "step.get_current_app",
                attrs={"step": self._step_count, "agent_type": self.__class__.__name__},
            ):
                current_app = await asyncio.to_thread(self.device.get_current_app)
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            yield {"type": "error", "data": {"message": f"Device error: {e}"}}
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

        # 2. 构建消息
        with trace_span(
            "step.build_message",
            attrs={"step": self._step_count, "agent_type": self.__class__.__name__},
        ):
            # 清除历史消息中残留的截图，保证本次请求只包含当前屏幕这一张图。
            self._context = [
                MessageBuilder.remove_images_from_message(message)
                for message in self._context
            ]

            screen_info = MessageBuilder.build_screen_info(current_app)
            if self._step_count == 1 and self._pending_task is not None:
                reference_notice = MessageBuilder.build_user_reference_images_notice(
                    len(self._pending_reference_images)
                )
                reference_section = (
                    f"\n\n** User Reference Images **\n\n{reference_notice}"
                    if reference_notice
                    else ""
                )
                text_content = (
                    f"{self._pending_task}{reference_section}\n\n{screen_info}"
                )
                self._pending_task = None
                images = [
                    {"mime_type": "image/png", "data": screenshot.base64_data},
                    *self._pending_reference_images,
                ]
                self._pending_reference_images = []
            else:
                text_content = f"{screen_info}"
                images = [{"mime_type": "image/png", "data": screenshot.base64_data}]
            self._context.append(
                MessageBuilder.create_user_message_with_images(
                    text=text_content,
                    images=images,
                )
            )

        # 3. 流式调用 OpenAI
        image_count = _count_image_parts(self._context)
        if image_count < 1:
            logger.warning(
                "Qwen request should carry at least one screenshot, got %d (step %d)",
                image_count,
                self._step_count,
            )

        try:
            if self.agent_config.verbose:
                msgs = get_messages(self.agent_config.lang)
                logger.debug(f"💭 {msgs['thinking']}:")

            thinking_parts = []
            raw_content = ""

            with trace_span(
                "step.llm",
                attrs={
                    "step": self._step_count,
                    "agent_type": self.__class__.__name__,
                    "model_name": self.model_config.model_name,
                    "message_count": len(self._context),
                },
            ):
                async for chunk_data in self._stream_openai(self._context):
                    if self._cancel_event.is_set():
                        raise asyncio.CancelledError()

                    if chunk_data["type"] in ["thinking", "reasoning"]:
                        thinking_parts.append(chunk_data["content"])
                        yield {
                            "type": "thinking",
                            "data": {"chunk": chunk_data["content"]},
                        }
                        if self.agent_config.verbose:
                            logger.debug(chunk_data["content"])

                    elif chunk_data["type"] == "raw":
                        raw_content += chunk_data["content"]
                    else:
                        logger.warning(
                            f"Unknown chunk type: {chunk_data['type']}, chunk_data: {chunk_data}"
                        )

            thinking = "".join(thinking_parts)

        except asyncio.CancelledError:
            logger.info(f"Step {self._step_count} cancelled during LLM call")
            raise

        except Exception as e:
            logger.error(f"LLM error: {e}")
            if self.agent_config.verbose:
                logger.debug(traceback.format_exc())
            yield {"type": "error", "data": {"message": f"Model error: {e}"}}
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
        with trace_span(
            "step.parse_action",
            attrs={"step": self._step_count, "agent_type": self.__class__.__name__},
        ):
            parsed_thinking, action_str = self.parser.parse_response(raw_content)
            if parsed_thinking:
                thinking = parsed_thinking

            try:
                action = self.parser.parse(action_str)
            except ValueError as e:
                if self.agent_config.verbose:
                    logger.warning(
                        f"Failed to parse action: {action_str}, err: {e}, treating as finish"
                    )
                action = {"_metadata": "finish", "message": action_str}

            if self.agent_config.verbose:
                logger.debug(f"raw_content: \n\n {raw_content}\n\n")
                logger.debug(f"thinking_parts: \n\n {thinking_parts}\n\n")
                logger.debug(f"parsed_thinking: \n\n{parsed_thinking}\n\n")
                logger.debug(f"action_str: \n\n{action_str}\n\n")
                logger.debug(f"action: \n\n{action}\n\n")

        if self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            logger.debug(f"🎯 {msgs['action']}:")
            logger.debug(json.dumps(action, ensure_ascii=False, indent=2))

        # Debug: draw red dot on screenshot for tap actions
        if self.agent_config.verbose and action.get("_metadata") == "do":
            action_name = action.get("action", "")
            element = action.get("element")
            if element and action_name in ("Tap", "Double Tap", "Long Press"):
                x = int(int(element[0]) / 1000 * screenshot.width)
                y = int(int(element[1]) / 1000 * screenshot.height)
                debug_path = self._draw_tap_debug(
                    screenshot.base64_data, x, y, action_name, self._step_count
                )
                if debug_path:
                    logger.debug(
                        f"[Debug] Tap marker drawn at ({x}, {y}) -> {debug_path}"
                    )

        # 5. 执行 action
        try:
            with trace_span(
                "step.execute_action",
                attrs={
                    "step": self._step_count,
                    "agent_type": self.__class__.__name__,
                    "action_name": action.get("action"),
                    "action_type": action.get("_metadata"),
                },
            ):
                result = await asyncio.to_thread(
                    self.action_handler.execute,
                    action,
                    screenshot.width,
                    screenshot.height,
                )
        except Exception as e:
            logger.error(f"Action execution error: {e}")
            if self.agent_config.verbose:
                logger.debug(traceback.format_exc())
            from AutoGLM_GUI.actions import ActionResult

            result = ActionResult(success=False, should_finish=True, message=str(e))

        # 6. 更新上下文
        with trace_span(
            "step.update_context",
            attrs={"step": self._step_count, "agent_type": self.__class__.__name__},
        ):
            self._context[-1] = MessageBuilder.remove_images_from_message(
                self._context[-1]
            )
            self._context.append(
                MessageBuilder.create_assistant_message(
                    f"<thought>{thinking}</thought><answer>{action_str}</answer>"
                )
            )

        # 7. 检查完成
        finished = action.get("_metadata") == "finish" or result.should_finish
        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            logger.debug(
                f"✅ {msgs['task_completed']}: "
                f"{result.message or action.get('message', msgs['done'])}"
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
                "screenshot": screenshot.base64_data if screenshot else None,
            },
        }

    async def _stream_openai(
        self, messages: list[dict[str, Any]]
    ) -> AsyncGenerator[dict[str, str], None]:
        """流式调用 OpenAI，yield thinking chunks。"""
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
        action_markers = ["<answer>", "finish(message=", "do(action="]
        in_action_phase = False

        try:
            async for chunk in stream:
                if self._cancel_event.is_set():
                    await stream.close()
                    raise asyncio.CancelledError()

                if len(chunk.choices) == 0:
                    continue

                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    yield {"type": "raw", "content": content}

                    if in_action_phase:
                        continue

                    buffer += content

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
            await stream.close()
