"""MAI Agent parser using XML tags and JSON."""

import json
import re
from typing import Any


SCALE_FACTOR = 999


class MAIParser:
    """Parse MAI Agent XML + JSON format outputs.

    Handles format like:
        <thinking>Reasoning process</thinking>
        <tool_call>{"name": "mobile_use", "arguments": {...}}</tool_call>

    Converts MAI-specific actions to standard ActionHandler format.
    Coordinate scale: 0-999 (automatically converted to 0-1000)
    """

    @property
    def coordinate_scale(self) -> int:
        return 999

    def parse(self, raw_response: str) -> dict[str, Any]:
        """Parse MAI agent XML+JSON output.

        Args:
            raw_response: Model output containing <thinking> and <tool_call> tags.

        Returns:
            Standardized action dictionary with coordinates converted to 0-1000 scale.

        Raises:
            ValueError: If parsing fails or content is invalid JSON.
        """
        text = raw_response.strip()

        if "</think>" in text and "</thinking>" not in text:
            text = text.replace("</think>", "</thinking>")
            text = "<thinking>" + text

        pattern = r"<thinking>(.*?)</thinking>.*?<tool_call>(.*?)</tool_call>"
        match = re.search(pattern, text, re.DOTALL)

        if not match:
            raise ValueError("Failed to find <thinking> and <tool_call> tags")

        tool_call_str = match.group(2).strip().strip('"')

        try:
            tool_call = json.loads(tool_call_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in tool_call: {e}") from e

        mai_action = tool_call.get("arguments", {})
        return self._convert_action(mai_action)

    def _convert_action(self, mai_action: dict[str, Any]) -> dict[str, Any]:
        """Convert MAI action format to standard ActionHandler format.

        MAI format: {"action": "click", "coordinate": [x, y]}
        Standard format: {"_metadata": "do", "action": "Tap", "element": [x, y]}
        """
        action_type = mai_action.get("action")

        if action_type == "terminate":
            status = mai_action.get("status", "success")
            return {
                "_metadata": "finish",
                "message": "Task completed" if status == "success" else "Task failed",
            }

        if action_type == "answer":
            return {
                "_metadata": "finish",
                "message": mai_action.get("text", ""),
            }

        if action_type == "wait":
            return {
                "_metadata": "do",
                "action": "Wait",
                "duration": "1 seconds",
            }

        if action_type == "system_button":
            button_name = mai_action.get("button", "")
            action_map = {
                "back": "Back",
                "home": "Home",
                "enter": "Enter",
            }
            return {
                "_metadata": "do",
                "action": action_map.get(button_name, "Back"),
            }

        coordinate = mai_action.get("coordinate")
        if coordinate:
            x = self._convert_coordinate(coordinate[0])
            y = self._convert_coordinate(coordinate[1])

            if action_type == "click":
                return {
                    "_metadata": "do",
                    "action": "Tap",
                    "element": [x, y],
                }
            elif action_type == "long_press":
                return {
                    "_metadata": "do",
                    "action": "Long Press",
                    "element": [x, y],
                }
            elif action_type == "double_click":
                return {
                    "_metadata": "do",
                    "action": "Double Tap",
                    "element": [x, y],
                }

        if action_type == "swipe":
            direction = mai_action.get("direction", "up")
            coordinate = mai_action.get("coordinate") or [0.5, 0.5]
            x = self._convert_coordinate(coordinate[0])
            y = self._convert_coordinate(coordinate[1])

            start, end = self._calculate_swipe_coordinates(direction, x, y)
            return {
                "_metadata": "do",
                "action": "Swipe",
                "start": start,
                "end": end,
            }

        if action_type == "drag":
            start_coord = mai_action.get("start_coordinate", [0, 0])
            end_coord = mai_action.get("end_coordinate", [0, 0])

            start = [
                self._convert_coordinate_from_scale_factor(start_coord[0]),
                self._convert_coordinate_from_scale_factor(start_coord[1]),
            ]
            end = [
                self._convert_coordinate_from_scale_factor(end_coord[0]),
                self._convert_coordinate_from_scale_factor(end_coord[1]),
            ]
            return {
                "_metadata": "do",
                "action": "Swipe",
                "start": start,
                "end": end,
            }

        if action_type == "type":
            return {
                "_metadata": "do",
                "action": "Type",
                "text": mai_action.get("text", ""),
            }

        if action_type == "open":
            return {
                "_metadata": "do",
                "action": "Launch",
                "app_name": mai_action.get("app", ""),
            }

        raise ValueError(f"Unknown MAI action type: {action_type}")

    def _convert_coordinate(self, value: float) -> int:
        """Convert MAI normalized coordinate [0, 1] to standard scale [0, 1000]."""
        return int(value * 1000)

    def _convert_coordinate_from_scale_factor(self, value: float) -> int:
        """Convert MAI scale factor coordinate [0, 999] to standard scale [0, 1000]."""
        return int((value / SCALE_FACTOR) * 1000)

    def _calculate_swipe_coordinates(
        self, direction: str, x: int, y: int
    ) -> tuple[list[int], list[int]]:
        """Calculate start and end coordinates for swipe based on direction."""
        swipe_distance = 300

        direction_map = {
            "up": ([x, y + swipe_distance], [x, y - swipe_distance]),
            "down": ([x, y - swipe_distance], [x, y + swipe_distance]),
            "left": ([x + swipe_distance, y], [x - swipe_distance, y]),
            "right": ([x - swipe_distance, y], [x + swipe_distance, y]),
        }

        return direction_map.get(direction, ([x, y], [x, y]))
