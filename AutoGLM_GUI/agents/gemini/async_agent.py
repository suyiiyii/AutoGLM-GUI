"""AsyncGeminiAgent - 通用视觉模型 Agent，使用 OpenAI 兼容的 function calling。

支持 Gemini、GPT-4o、Claude 等任何支持 vision + tool use 的模型，
通过 OpenAI 兼容 API 端点接入。
"""

import asyncio
import json
import traceback
from collections.abc import AsyncGenerator
from typing import Any

from AutoGLM_GUI.actions import ActionResult
from AutoGLM_GUI.agents.base import AsyncAgentBase
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder

from .action_mapper import tool_call_to_action
from .prompts import get_system_prompt
from .tools import DEVICE_TOOLS


class AsyncGeminiAgent(AsyncAgentBase):
    """通用视觉模型 Agent，使用 function calling 而非自定义格式解析。"""

    def _get_default_system_prompt(self, lang: str) -> str:
        return get_system_prompt(lang)

    def _prepare_initial_context(
        self, task: str, screenshot_base64: str, current_app: str
    ) -> None:
        self._context.append(
            MessageBuilder.create_user_message(
                text=f"{task}\n\nCurrent app: {current_app}",
                image_base64=screenshot_base64,
            )
        )

    async def _execute_step(self) -> AsyncGenerator[dict[str, Any], None]:
        """执行单步：调用 LLM → 解析 tool call → 执行动作。"""
        self._step_count += 1

        # 1. 获取截图（非首步）
        if self._step_count > 1:
            try:
                screenshot = await asyncio.to_thread(self.device.get_screenshot)
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

            self._context.append(
                MessageBuilder.create_user_message(
                    text=f"Current app: {current_app}",
                    image_base64=screenshot.base64_data,
                )
            )

        # 2. 调用 LLM with tools
        try:
            thinking, tool_name, tool_args = await self._call_llm_with_tools()
        except asyncio.CancelledError:
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

        if thinking:
            yield {"type": "thinking", "data": {"chunk": thinking}}

        # 3. 转换 tool call → action
        action = tool_call_to_action(tool_name, tool_args)

        if self.agent_config.verbose:
            logger.debug(f"🎯 Tool call: {tool_name}({tool_args})")
            logger.debug(f"   Action: {json.dumps(action, ensure_ascii=False)}")

        # 4. 执行 action
        screenshot = None
        try:
            screenshot = await asyncio.to_thread(self.device.get_screenshot)
            result = await asyncio.to_thread(
                self.action_handler.execute,
                action,
                screenshot.width,
                screenshot.height,
            )
        except Exception as e:
            logger.error(f"Action execution error: {e}")
            result = ActionResult(success=False, should_finish=True, message=str(e))

        # 5. 更新上下文
        if len(self._context) > 1:
            self._context[-1] = MessageBuilder.remove_images_from_message(
                self._context[-1]
            )

        self._context.append(
            {
                "role": "assistant",
                "content": thinking or "",
                "tool_calls": [
                    {
                        "id": f"call_{self._step_count}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args),
                        },
                    }
                ],
            }
        )
        self._context.append(
            {
                "role": "tool",
                "tool_call_id": f"call_{self._step_count}",
                "content": json.dumps(
                    {"success": result.success, "message": result.message or "OK"}
                ),
            }
        )

        # 6. 检查完成
        finished = action.get("_metadata") == "finish" or result.should_finish

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

    async def _call_llm_with_tools(self) -> tuple[str, str, dict[str, Any]]:
        """调用 LLM，返回 (thinking, tool_name, tool_args)。"""
        if self._cancel_event.is_set():
            raise asyncio.CancelledError()

        response = await self.openai_client.chat.completions.create(
            messages=self._context,  # type: ignore[arg-type]
            model=self.model_config.model_name,
            max_tokens=self.model_config.max_tokens,
            temperature=self.model_config.temperature,
            tools=DEVICE_TOOLS,  # type: ignore[arg-type]
            tool_choice="required",
        )

        choice = response.choices[0]
        message = choice.message

        thinking = message.content or ""

        if message.tool_calls and len(message.tool_calls) > 0:
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name  # type: ignore[union-attr]
            try:
                tool_args = json.loads(tool_call.function.arguments)  # type: ignore[union-attr]
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Failed to parse tool arguments for {tool_name}: {e}. "
                    f"Raw: {tool_call.function.arguments!r}"  # type: ignore[union-attr]
                )
                tool_args = {}
            return thinking, tool_name, tool_args

        logger.warning("Model did not return a tool call, treating as finish")
        return thinking, "finish", {"message": thinking or "No action returned"}
