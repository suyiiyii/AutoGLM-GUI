"""Prompt templates for agents."""

from pathlib import Path

# Import MAI prompt from new location
from AutoGLM_GUI.agents.mai.prompts import MAI_MOBILE_SYSTEM_PROMPT

# Import from parent-level prompts.py file
# When prompts/ directory exists, Python prioritizes it over prompts.py
# We need to import from sibling prompts.py file
parent_dir = Path(__file__).parent.parent
prompts_file = parent_dir / "prompts.py"

if prompts_file.exists():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_prompts_legacy", prompts_file)
    if spec and spec.loader:
        _prompts_legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_prompts_legacy)
        MCP_SYSTEM_PROMPT_ZH = getattr(_prompts_legacy, "MCP_SYSTEM_PROMPT_ZH", "")
        MCP_SYSTEM_PROMPT_EN = getattr(_prompts_legacy, "MCP_SYSTEM_PROMPT_EN", "")
else:
    # Fallback if file doesn't exist
    MCP_SYSTEM_PROMPT_ZH = ""
    MCP_SYSTEM_PROMPT_EN = ""

__all__ = [
    "MAI_MOBILE_SYSTEM_PROMPT",
    "MCP_SYSTEM_PROMPT_ZH",
    "MCP_SYSTEM_PROMPT_EN",
]
