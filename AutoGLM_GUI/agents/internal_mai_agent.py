"""Re-export InternalMAIAgent from new location.

Backward compatibility shim. Import from AutoGLM_GUI.agents.mai.agent instead.
"""

from AutoGLM_GUI.agents.mai.agent import InternalMAIAgent

__all__ = ["InternalMAIAgent"]
