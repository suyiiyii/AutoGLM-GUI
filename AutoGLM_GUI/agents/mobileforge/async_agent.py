"""Async agent for MobileForge-compatible Qwen-VL models."""

from __future__ import annotations

from collections.abc import Callable

from .parser import MobileForgeParser
from .prompts import SYSTEM_PROMPT
from AutoGLM_GUI.agents.qwen.async_agent import AsyncQwenAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.device_protocol import DeviceProtocol


class AsyncMobileForgeAgent(AsyncQwenAgent):
    """Reuse the reliable Qwen execution loop with MobileForge wire format."""

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        device: DeviceProtocol,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        super().__init__(
            model_config=model_config,
            agent_config=agent_config,
            device=device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )
        self.parser = MobileForgeParser()
        self._action_markers = ["<tool_call>"]

    def _get_default_system_prompt(self, lang: str) -> str:  # noqa: ARG002
        return SYSTEM_PROMPT

    def _format_assistant_context(
        self, raw_content: str, thinking: str, action_str: str
    ) -> str:  # noqa: ARG002
        # Native history matters for models fine-tuned on MobileForge traces.
        return raw_content
