"""Re-export MAIParser from new location.

Backward compatibility shim. Import from AutoGLM_GUI.agents.mai.parser instead.
"""

from AutoGLM_GUI.agents.mai.parser import MAIParser, MAIParseError

__all__ = ["MAIParser", "MAIParseError"]
