import ast
import re
from typing import Any


class QwenParser:
    """Parse Qwen model output into structured actions.

    Supports three action formats:
    - do(action="Tap", element=[x, y])
    - finish(message="done")
    - info(question="what to send?")
    """

    @property
    def coordinate_scale(self) -> int:
        return 1000

    def parse(self, action_str: str) -> dict[str, Any]:
        """Parse a raw action string into a structured dictionary.

        Args:
            action_str: Raw action string (e.g., "do(action=\"Tap\", element=[100, 200])")

        Returns:
            dict with '_metadata' key indicating action type.

        Raises:
            ValueError: If parsing fails.
        """
        response = action_str.strip()
        response = response.strip("<answer>").strip("</answer>")

        try:
            if response.startswith("do"):
                return self._parse_do(response)
            elif response.startswith("info"):
                return self._parse_info(response)
            elif response.startswith("finish"):
                return self._parse_finish(response)
            else:
                raise ValueError(f"Unknown action format: {response}")
        except (SyntaxError, ValueError):
            response = self._re_parse(response)
            if response.startswith("do"):
                return self._parse_do(response)
            elif response.startswith("info"):
                return self._parse_info(response)
            elif response.startswith("finish"):
                return self._parse_finish(response)
            raise ValueError(f"Failed to parse action after repair: {response}")

    def _parse_do(self, response: str) -> dict[str, Any]:
        try:
            tree = ast.parse(response, mode="eval")
            if not isinstance(tree.body, ast.Call):
                raise ValueError("Expected a function call")
            call = tree.body
            result: dict[str, Any] = {"_metadata": "do"}
            for keyword in call.keywords:
                if keyword.arg is not None:
                    result[keyword.arg] = ast.literal_eval(keyword.value)
            return result
        except (SyntaxError, ValueError) as e:
            raise ValueError(f"Failed to parse do() action: {e}") from e

    def _parse_info(self, response: str) -> dict[str, Any]:
        try:
            tree = ast.parse(response, mode="eval")
            if not isinstance(tree.body, ast.Call):
                raise ValueError("Expected a function call")
            call = tree.body
            result: dict[str, Any] = {"_metadata": "info"}
            for keyword in call.keywords:
                if keyword.arg is not None:
                    result[keyword.arg] = ast.literal_eval(keyword.value)
            return result
        except (SyntaxError, ValueError) as e:
            raise ValueError(f"Failed to parse info() action: {e}") from e

    def _parse_finish(self, response: str) -> dict[str, Any]:
        try:
            tree = ast.parse(response, mode="eval")
            if not isinstance(tree.body, ast.Call):
                raise ValueError("Expected a function call")
            call = tree.body
            result: dict[str, Any] = {"_metadata": "finish"}
            for keyword in call.keywords:
                if keyword.arg is not None:
                    result[keyword.arg] = ast.literal_eval(keyword.value)
            return result
        except (SyntaxError, ValueError):
            # Fallback: 简单提取消息内容（兼容消息中包含引号的情况）
            message = response.replace("finish(message=", "")
            # 移除首尾引号和末尾括号
            if message.startswith('"') and message.endswith('")'):
                message = message[1:-2]
            elif message.startswith("'") and message.endswith("')"):
                message = message[1:-2]
            return {"_metadata": "finish", "message": message}

    @staticmethod
    def _re_parse(response: str) -> str:
        """Fix common bracket formatting errors with regex."""
        answer_matches = re.findall(
            r"<answer>(.*?)(?:</answer>|$)", response, re.DOTALL
        )
        if answer_matches:
            response = answer_matches[-1].strip()

        response = re.sub(
            r"\[(\s*-?\d+(?:\s*,\s*-?\d+)*\s*)\)(?=\s*\))", r"[\1])", response
        )
        response = re.sub(
            r"\[(\s*-?\d+(?:\s*,\s*-?\d+)*\s*)\)(?=\s*,)", r"[\1]", response
        )
        response = re.sub(r"\[(\s*-?\d+(?:\s*,\s*-?\d+)*\s*)\)\s*$", r"[\1])", response)
        return response

    @staticmethod
    def parse_response(content: str) -> tuple[str, str]:
        """Parse raw model output into (thinking, action) parts.

        Three-tier strategy:
        1. <answer> tags (primary anchor)
        2. Keyword fallback: finish(message= / do(action=
        3. Return empty thinking + full content as action

        Args:
            content: Full raw model response text.

        Returns:
            (thinking_text, action_text) tuple.
        """

        if "<answer>" in content:
            answer_start = content.find("<answer>")
            answer_end = content.find("</answer>", answer_start)
            if answer_end == -1:
                answer_end = len(content)
            action = content[answer_start + len("<answer>") : answer_end].strip()
            thinking_part = content[:answer_start]
            thinking_part = (
                thinking_part.replace("<think>", "")
                .replace("</think>", "")
                .replace("<thought>", "")
                .replace("</thought>", "")
                .strip()
            )
            return thinking_part, action

        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = (
                parts[0]
                .replace("<think>", "")
                .replace("</think>", "")
                .replace("<thought>", "")
                .replace("</thought>", "")
                .strip()
            )
            action = "finish(message=" + parts[1].strip()
            return thinking, action

        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = (
                parts[0]
                .replace("<think>", "")
                .replace("</think>", "")
                .replace("<thought>", "")
                .replace("</thought>", "")
                .strip()
            )
            action = "do(action=" + parts[1].strip()
            return thinking, action

        return "", content
