"""Translate MobileForge JSON tool calls to AutoGLM GUI actions."""

from __future__ import annotations

import json
import re
from typing import Any


class MobileForgeParser:
    """Parse ``<tool_call>`` JSON without evaluating model-produced code."""

    @property
    def coordinate_scale(self) -> int:
        return 1000

    @staticmethod
    def parse_response(content: str) -> tuple[str, str]:
        thinking_match = re.search(r"<thinking>(.*?)</thinking>", content, re.DOTALL)
        thinking = thinking_match.group(1).strip() if thinking_match else ""
        call_match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL)
        if not call_match:
            # Keep the base agent's standard parse-error/finish behavior.
            return thinking, content
        return thinking, call_match.group(1)

    def parse(self, action_str: str) -> dict[str, Any]:
        try:
            tool_call = json.loads(action_str)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid MobileForge tool-call JSON") from exc
        if not isinstance(tool_call, dict):
            raise ValueError("MobileForge tool call must be a JSON object")

        action = tool_call.get("action")
        if not isinstance(action, str):
            raise ValueError("MobileForge tool call needs a string action")

        if action in {"answer", "terminate"}:
            message = tool_call.get("text", tool_call.get("message", "Task completed"))
            return {"_metadata": "finish", "message": str(message)}
        if action == "click":
            return self._point_action("Tap", tool_call)
        if action == "long_press":
            return self._point_action("Long Press", tool_call)
        if action == "swipe":
            return {
                "_metadata": "do",
                "action": "Swipe",
                "start": self._point(tool_call.get("start"), "start"),
                "end": self._point(tool_call.get("end"), "end"),
            }
        if action == "type":
            text = tool_call.get("text")
            if not isinstance(text, str):
                raise ValueError("type action needs text")
            return {"_metadata": "do", "action": "Type", "text": text}
        if action == "open":
            app = tool_call.get("app")
            if not isinstance(app, str) or not app:
                raise ValueError("open action needs app")
            return {"_metadata": "do", "action": "Launch", "app": app}
        if action == "system_button":
            button = str(tool_call.get("button", "")).lower()
            names = {"back": "Back", "home": "Home"}
            if button not in names:
                raise ValueError("system_button must be back or home")
            return {"_metadata": "do", "action": names[button]}
        if action == "wait":
            duration = tool_call.get("duration", 1)
            if not isinstance(duration, int | float) or duration < 0:
                raise ValueError("wait duration must be a non-negative number")
            return {"_metadata": "do", "action": "Wait", "duration": f"{duration} seconds"}
        raise ValueError(f"Unsupported MobileForge action: {action}")

    def _point_action(self, action: str, tool_call: dict[str, Any]) -> dict[str, Any]:
        return {
            "_metadata": "do",
            "action": action,
            "element": self._point(tool_call.get("coordinate"), "coordinate"),
        }

    @staticmethod
    def _point(value: Any, name: str) -> list[int]:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or any(not isinstance(item, int | float) for item in value)
        ):
            raise ValueError(f"{name} must be a two-number coordinate")
        return [max(0, min(1000, int(value[0]))), max(0, min(1000, int(value[1])))]
