"""PhoneAgent parser using standard AST parsing."""

import ast
from typing import Any


class PhoneAgentParser:
    """Parse PhoneAgent function-call style outputs using ast.parse.

    Handles the same format as GLM but with simpler AST-based parsing.
    Includes special handling for Type action to avoid parsing issues.
    Coordinate scale: 0-1000
    """

    @property
    def coordinate_scale(self) -> int:
        return 1000

    def parse(self, raw_response: str) -> dict[str, Any]:
        response = raw_response.strip()

        if response.startswith('do(action="Type"') or response.startswith(
            'do(action="Type_Name"'
        ):
            text = response.split("text=", 1)[1][1:-2]
            action = {"_metadata": "do", "action": "Type", "text": text}
            return action
        elif response.startswith("do"):
            try:
                response = response.replace("\n", "\\n")
                response = response.replace("\r", "\\r")
                response = response.replace("\t", "\\t")

                tree = ast.parse(response, mode="eval")
                if not isinstance(tree.body, ast.Call):
                    raise ValueError("Expected a function call")

                call = tree.body
                action = {"_metadata": "do"}
                for keyword in call.keywords:
                    key = keyword.arg
                    if key is None:
                        raise ValueError("Keyword argument name missing")
                    value = ast.literal_eval(keyword.value)
                    action[key] = value

                return action
            except (SyntaxError, ValueError) as e:
                raise ValueError(f"Failed to parse do() action: {e}") from e

        elif response.startswith("finish"):
            action = {
                "_metadata": "finish",
                "message": response.replace("finish(message=", "")[1:-2],
            }
            return action
        else:
            raise ValueError(f"Failed to parse action: {response}")
