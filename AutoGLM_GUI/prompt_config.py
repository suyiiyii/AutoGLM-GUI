"""Configuration helpers for prompts and i18n messages.

This module provides helper functions that were originally in phone_agent.config,
now extracted to avoid dependency on phone_agent.
"""

from AutoGLM_GUI.i18n import MESSAGES_EN, MESSAGES_ZH, get_message, get_messages
from AutoGLM_GUI.agents.glm import SYSTEM_PROMPT_EN, SYSTEM_PROMPT_ZH


def get_system_prompt(lang: str = "cn") -> str:
    """
    Get system prompt by language.

    Args:
        lang: Language code, 'cn' for Chinese, 'en' for English.

    Returns:
        System prompt string.
    """
    if lang == "en":
        return SYSTEM_PROMPT_EN
    return SYSTEM_PROMPT_ZH


SYSTEM_PROMPT = SYSTEM_PROMPT_ZH

__all__ = [
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "SYSTEM_PROMPT_EN",
    "get_system_prompt",
    "get_messages",
    "get_message",
    "MESSAGES_EN",
    "MESSAGES_ZH",
]
