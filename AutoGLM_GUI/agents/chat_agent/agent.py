"""ChatAgent - 纯对话模式 Agent，不涉及 GUI 操作。

支持文本/图片多模态输入、流式输出、对话上下文维护。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder


class ChatAgent:
    """纯对话 Agent，直接调用 LLM/VLM 进行对话，不操作设备。"""

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
    ):
        self.model_config = model_config
        self.agent_config = agent_config

        self.openai_client = AsyncOpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            timeout=120,
        )

        self._cancel_event = asyncio.Event()
        self._context: list[dict[str, Any]] = []
        self._user_image_attachments: list[dict[str, str]] = []
        self._step_count = 0
        self._is_running = False

        self._reset_context()

    def _reset_context(self) -> None:
        """重置对话上下文。"""
        system_prompt = self.agent_config.system_prompt
        if system_prompt is None:
            system_prompt = self._get_default_system_prompt(self.agent_config.lang)

        # self._context = [MessageBuilder.create_system_message(system_prompt)]
        self._context = []
        self._step_count = 0

    @staticmethod
    def _get_default_system_prompt(lang: str) -> str:
        """返回默认 system prompt。"""
        if lang == "cn":
            return (
                "你是一个有帮助的 AI 助手。"
                "请根据用户的问题提供清晰、准确的回答。"
                "如果用户提供了图片，请仔细观察图片内容并基于图片进行回答。"
            )
        return (
            "You are a helpful AI assistant. "
            "Please provide clear and accurate answers based on the user's questions. "
            "If the user provides images, carefully observe the image content and answer based on it."
        )

    def set_user_image_attachments(self, attachments: list[dict[str, Any]]) -> None:
        """设置用户上传的图片附件。"""
        self._user_image_attachments = [
            {
                "mime_type": str(a.get("mime_type", "image/png")),
                "data": str(a.get("data", "")),
            }
            for a in attachments
            if a.get("data")
        ]

    # ==================== AsyncAgent Protocol ====================

    async def run(self, task: str) -> str:
        """运行完整任务，返回最终结果。"""
        result = ""
        async for event in self.stream(task):
            if event["type"] == "done":
                result = event["data"].get("message", "")
            elif event["type"] == "error":
                result = event["data"].get("message", "Error")
        return result

    async def stream(self, task: str) -> AsyncGenerator[dict[str, Any], None]:
        """流式执行对话任务。

        Yields:
            thinking: {"chunk": str}
            done: {"message": str, "steps": int, "success": bool}
            error: {"message": str}
            cancelled: {"message": str}
        """
        self._is_running = True
        self._cancel_event.clear()
        self._step_count += 1

        try:
            # 构建用户消息（支持图片附件）
            images = self._user_image_attachments.copy()
            self._user_image_attachments = []  # 消费后清空

            user_message = MessageBuilder.create_user_message_with_images(
                text=task,
                images=images,
            )
            self._context.append(user_message)

            logger.debug(f"self.model_config: {self.model_config}")

            # 流式调用 LLM
            stream = await self.openai_client.chat.completions.create(
                messages=self._context,  # type: ignore[arg-type]
                model=self.model_config.model_name,
                max_tokens=self.model_config.max_tokens,
                temperature=self.model_config.temperature,
                top_p=self.model_config.top_p,
                frequency_penalty=self.model_config.frequency_penalty,
                extra_body=self.model_config.extra_body,
                stream=True,
            )

            raw_content = ""
            reasoning_buffer = ""
            content_buffer = ""
            in_reasoning = False
            chunk_count = 0
            finish_reason = None
            try:
                async for chunk in stream:
                    if self._cancel_event.is_set():
                        await stream.close()
                        raise asyncio.CancelledError()

                    if len(chunk.choices) == 0:
                        logger.debug(
                            f"[ChatAgent] Empty choices in chunk #{chunk_count}"
                        )
                        continue

                    delta = chunk.choices[0].delta
                    chunk_count += 1

                    # 记录 finish_reason（如 length 表示 max_tokens 耗尽）
                    choice = chunk.choices[0]
                    if getattr(choice, "finish_reason", None):
                        finish_reason = choice.finish_reason

                    # 支持原生 reasoning_content（如 Qwen3.6）和 <think> 标签两种模式
                    reasoning_delta = (
                        getattr(delta, "reasoning_content", None)
                        or getattr(delta, "reasoning", None)
                        or getattr(delta, "thinking", None)
                    )
                    content_delta = getattr(delta, "content", None)

                    logger.debug(
                        f"[ChatAgent] chunk #{chunk_count}: reasoning_delta={reasoning_delta!r} "
                        f"content_delta={content_delta!r} raw_content_len={len(raw_content)} "
                        f"reasoning_buf_len={len(reasoning_buffer)} in_reasoning={in_reasoning}"
                    )

                    if reasoning_delta:
                        reasoning_buffer += reasoning_delta
                        yield {
                            "type": "thinking",
                            "data": {"chunk": reasoning_buffer},
                        }
                        in_reasoning = True

                    if content_delta:
                        raw_content += content_delta
                        # 如果之前处于 reasoning 阶段，现在收到 content，说明 reasoning 结束
                        if in_reasoning:
                            in_reasoning = False
                        # 支持 <think> 标签模式（仅当没有原生 reasoning_content 时）
                        if not reasoning_buffer:
                            thinking, answer = self._parse_think_tags(raw_content)
                            if thinking:
                                yield {
                                    "type": "thinking",
                                    "data": {"chunk": thinking},
                                }
                            stream_content = answer if answer else raw_content
                        else:
                            # 原生 reasoning 模式：content 就是正文
                            stream_content = raw_content
                        if stream_content:
                            content_buffer = stream_content
                            yield {
                                "type": "content",
                                "data": {"chunk": content_buffer},
                            }
            finally:
                await stream.close()

            # 解析最终内容
            thinking, answer = self._parse_think_tags(raw_content)

            logger.info(
                f"[ChatAgent] stream finished: chunks={chunk_count} raw_content_len={len(raw_content)} "
                f"reasoning_buf_len={len(reasoning_buffer)} thinking_len={len(thinking)} "
                f"answer_len={len(answer)} in_reasoning={in_reasoning} "
                f"finish_reason={finish_reason}"
            )

            # 检测 max_tokens 耗尽的情况
            if finish_reason == "length" and not raw_content:
                error_msg = (
                    "模型思考过程过长，已达到 max_tokens 限制，未能生成正文回复。"
                    f"当前 max_tokens={self.model_config.max_tokens}，"
                    "建议增加 max_tokens 或简化问题。"
                )
                logger.warning(f"[ChatAgent] {error_msg}")
                yield {
                    "type": "error",
                    "data": {"message": error_msg},
                }
                yield {
                    "type": "done",
                    "data": {
                        "message": error_msg,
                        "steps": self._step_count,
                        "success": False,
                    },
                }
                return

            # 将助手回复加入上下文（保留原始内容，包含 think 标签）
            self._context.append(MessageBuilder.create_assistant_message(raw_content))

            final_message = answer if answer else raw_content
            yield {
                "type": "done",
                "data": {
                    "message": final_message,
                    "steps": self._step_count,
                    "success": True,
                },
            }

        except asyncio.CancelledError:
            logger.info("[ChatAgent] stream cancelled by user")
            yield {
                "type": "cancelled",
                "data": {"message": "Task cancelled by user"},
            }
            raise
        except Exception as e:
            logger.error(f"[ChatAgent] stream error: {e}", exc_info=True)
            yield {"type": "error", "data": {"message": str(e)}}
            yield {
                "type": "done",
                "data": {
                    "message": str(e),
                    "steps": self._step_count,
                    "success": False,
                },
            }
        finally:
            self._is_running = False

    @staticmethod
    def _parse_think_tags(content: str) -> tuple[str, str]:
        """解析 <think> 标签，分离思考内容和最终答案。

        Returns:
            (thinking_content, final_answer)
        """
        # 匹配 <think>...</think>，支持多行
        match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            # 移除 think 标签后的内容作为最终答案
            answer = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return thinking, answer
        return "", content.strip()

    async def cancel(self) -> None:
        """取消当前执行。"""
        self._cancel_event.set()

    def reset(self) -> None:
        """重置状态。"""
        self._reset_context()
        self._user_image_attachments = []
        self._is_running = False

    def step(self, task: str | None = None) -> Any:
        """对话模式不支持单步执行。"""
        raise NotImplementedError("ChatAgent does not support step()")

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def context(self) -> list[dict[str, Any]]:
        return list(self._context)

    @property
    def is_running(self) -> bool:
        return self._is_running
