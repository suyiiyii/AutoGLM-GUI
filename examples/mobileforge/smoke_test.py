"""Offline validation for MobileForge protocol responses.

Run: uv run python examples/mobileforge/smoke_test.py
"""

from AutoGLM_GUI.agents.mobileforge.parser import MobileForgeParser


def main() -> None:
    parser = MobileForgeParser()
    response = (
        "<thinking>I should tap Search.</thinking>"
        '<tool_call>{"name":"mobile_use","arguments":'
        '{"action":"click","coordinate":[500,120]}}</tool_call>'
    )
    thinking, action_text = parser.parse_response(response)
    action = parser.parse(action_text)
    assert thinking == "I should tap Search."
    assert action == {"_metadata": "do", "action": "Tap", "element": [500, 120]}
    print("MobileForge protocol smoke test passed")


if __name__ == "__main__":
    main()
