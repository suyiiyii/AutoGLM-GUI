"""Tool-call to action mapping for Gemini Agent."""

from typing import Any


class InvalidToolCallError(ValueError):
    """Raised when a model tool call cannot be mapped to a device action."""

    def __init__(self, tool_name: str, arguments: dict[str, Any], message: str):
        super().__init__(message)
        self.tool_name = tool_name
        self.arguments = arguments
        self.message = message


def _require_int(args: dict[str, Any], key: str) -> int:
    """Extract and validate an integer argument from tool call args."""
    val = args.get(key)
    if val is None:
        raise ValueError(f"Missing required argument: '{key}'")
    if not isinstance(val, (int, float)):
        raise ValueError(
            f"Expected number for '{key}', got {type(val).__name__}: {val!r}"
        )
    return int(val)


def _require_str(args: dict[str, Any], key: str) -> str:
    """Extract and validate a string argument from tool call args."""
    val = args.get(key)
    if val is None:
        raise ValueError(f"Missing required argument: '{key}'")
    if not isinstance(val, str):
        raise ValueError(
            f"Expected string for '{key}', got {type(val).__name__}: {val!r}"
        )
    return val


def tool_call_to_action(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Convert a function call to an ActionHandler-compatible action dict.

    Args:
        tool_name: The function name called by the model.
        arguments: The parsed arguments dict.

    Returns:
        Action dict compatible with ActionHandler.execute().
    """
    if tool_name == "finish":
        return {
            "_metadata": "finish",
            "message": arguments.get("message", "Task completed"),
        }

    try:
        return _build_action(tool_name, arguments)
    except (ValueError, KeyError) as e:
        raise InvalidToolCallError(tool_name, arguments, str(e)) from e


def _build_action(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Build action dict with validated arguments."""
    if tool_name == "tap":
        return {
            "_metadata": "do",
            "action": "Tap",
            "element": [_require_int(args, "x"), _require_int(args, "y")],
        }

    if tool_name == "double_tap":
        return {
            "_metadata": "do",
            "action": "Double Tap",
            "element": [_require_int(args, "x"), _require_int(args, "y")],
        }

    if tool_name == "long_press":
        return {
            "_metadata": "do",
            "action": "Long Press",
            "element": [_require_int(args, "x"), _require_int(args, "y")],
        }

    if tool_name == "swipe":
        return {
            "_metadata": "do",
            "action": "Swipe",
            "start": [_require_int(args, "start_x"), _require_int(args, "start_y")],
            "end": [_require_int(args, "end_x"), _require_int(args, "end_y")],
        }

    if tool_name == "type_text":
        return {"_metadata": "do", "action": "Type", "text": _require_str(args, "text")}

    if tool_name == "launch_app":
        return {
            "_metadata": "do",
            "action": "Launch",
            "app": _require_str(args, "app_name"),
        }

    if tool_name == "back":
        return {"_metadata": "do", "action": "Back"}

    if tool_name == "home":
        return {"_metadata": "do", "action": "Home"}

    if tool_name == "wait":
        return {
            "_metadata": "do",
            "action": "Wait",
            "duration": args.get("duration", "1 seconds"),
        }

    raise InvalidToolCallError(tool_name, args, f"Unknown tool: {tool_name}")
