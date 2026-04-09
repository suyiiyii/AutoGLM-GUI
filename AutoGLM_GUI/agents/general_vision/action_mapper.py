"""Preferred action-mapper entry point for the general vision agent."""

from ..gemini.action_mapper import tool_call_to_action

__all__ = ["tool_call_to_action"]
