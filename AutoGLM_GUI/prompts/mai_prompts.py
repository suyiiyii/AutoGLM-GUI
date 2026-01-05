"""Re-export MAI prompt from new location.

Backward compatibility shim. Import from AutoGLM_GUI.agents.mai.prompts instead.
"""

from AutoGLM_GUI.agents.mai.prompts import MAI_MOBILE_SYSTEM_PROMPT

__all__ = ["MAI_MOBILE_SYSTEM_PROMPT"]
