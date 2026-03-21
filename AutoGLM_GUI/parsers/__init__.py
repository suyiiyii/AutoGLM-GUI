"""Action parsers for different agent types.

This module provides parser implementations for converting model outputs
into standardized action dictionaries that can be executed by ActionHandler.

Each agent type has its own parser implementation:
- GLMParser: For GLM-based agents (enhanced AST parsing)
- MAIParser: For MAI agent (XML + JSON parsing)
"""

from AutoGLM_GUI.agents.glm.parser import GLMParser
from AutoGLM_GUI.agents.mai.parser import MAIParser

__all__ = [
    "GLMParser",
    "MAIParser",
]
