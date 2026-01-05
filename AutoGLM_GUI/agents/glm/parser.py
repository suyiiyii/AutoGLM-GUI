import ast
from typing import Any


class GLMParser:
    @property
    def coordinate_scale(self) -> int:
        return 1000

    def parse(self, raw_response: str) -> dict[str, Any]:
        action_str = raw_response.strip()

        if action_str.startswith("finish("):
            return self._parse_finish(action_str)
        if action_str.startswith("do("):
            return self._parse_do(action_str)
        raise ValueError(f"Unknown action format: {action_str}")

    def _parse_finish(self, action_str: str) -> dict[str, Any]:
        try:
            params = self._extract_params(action_str, "finish")
            return {
                "_metadata": "finish",
                "message": params.get("message", "Task completed"),
            }
        except Exception as e:
            raise ValueError(f"Failed to parse finish action: {e}") from e

    def _parse_do(self, action_str: str) -> dict[str, Any]:
        try:
            params = self._extract_params(action_str, "do")
            action_name = params.get("action", "")

            result = {
                "_metadata": "do",
                "action": action_name,
            }

            for key, value in params.items():
                if key != "action":
                    result[key] = value

            return result
        except Exception as e:
            raise ValueError(f"Failed to parse do action: {e}") from e

    def _extract_params(self, action_str: str, function_name: str) -> dict[str, Any]:
        prefix = f"{function_name}("
        if not action_str.startswith(prefix):
            raise ValueError(f"Action does not start with {prefix}")

        params_str = action_str[len(prefix) : -1]

        params: dict[str, Any] = {}
        current_key = None
        current_value = ""
        in_quotes = False
        quote_char = None
        bracket_depth = 0
        i = 0

        while i < len(params_str):
            char = params_str[i]

            if char in ('"', "'") and (i == 0 or params_str[i - 1] != "\\"):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None

            if not in_quotes:
                if char in ("[", "{"):
                    bracket_depth += 1
                elif char in ("]", "}"):
                    bracket_depth -= 1

                if char == "=" and bracket_depth == 0:
                    current_key = current_value.strip()
                    current_value = ""
                    i += 1
                    continue

                if char == "," and bracket_depth == 0:
                    if current_key:
                        params[current_key] = self._parse_value(current_value.strip())
                        current_key = None
                        current_value = ""
                    i += 1
                    continue

            current_value += char
            i += 1

        if current_key:
            params[current_key] = self._parse_value(current_value.strip())

        return params

    def _parse_value(self, value_str: str) -> Any:
        value_str = value_str.strip()

        if not value_str:
            return ""

        try:
            return ast.literal_eval(value_str)
        except (ValueError, SyntaxError):
            return value_str
