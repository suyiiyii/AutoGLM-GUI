from AutoGLM_GUI.agents.glm import SYSTEM_PROMPT_EN, SYSTEM_PROMPT_ZH
from AutoGLM_GUI.i18n import get_message, get_messages


def get_system_prompt(lang: str = "cn") -> str:
    if lang == "en":
        return SYSTEM_PROMPT_EN
    return SYSTEM_PROMPT_ZH


__all__ = [
    "get_system_prompt",
    "get_messages",
    "get_message",
]
