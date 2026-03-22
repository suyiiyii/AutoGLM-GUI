"""Browser-driven end-to-end tests for the local development stack.

This module exercises the real web UI in a browser, instead of calling the
backend APIs directly like ``test_local_e2e.py``.
"""

from pathlib import Path

import pytest


@pytest.mark.integration
class TestWebLocalE2E:
    """UI-driven E2E coverage using the local backend + Vite frontend."""

    @pytest.mark.release_gate
    def test_meituan_message_scenario_via_browser(
        self,
        local_server: dict,
        frontend_dev_server: dict,
        browser_page,
        mock_llm_client,
        mock_agent_server: str,
        test_client,
        sample_test_case: Path,
    ):
        """Run the Meituan scenario through the browser UI."""
        test_client.load_scenario(str(sample_test_case))

        page = browser_page
        frontend_url = frontend_dev_server["url"]
        llm_url = local_server["llm_url"]

        page.goto(f"{frontend_url}/chat", wait_until="networkidle")

        # Configure the model through the settings dialog.
        page.get_by_test_id("open-config-dialog").click()
        page.get_by_test_id("config-dialog").wait_for(state="visible")
        page.get_by_test_id("config-base-url").fill(f"{llm_url}/v1")
        page.get_by_test_id("config-model-name").fill("mock-glm-model")
        page.get_by_test_id("config-api-key").fill("mock-key")
        page.get_by_test_id("save-config").click()
        page.get_by_test_id("config-dialog").wait_for(state="hidden")

        # Add the mock remote device through the UI.
        page.get_by_test_id("open-add-device-dialog").click()
        page.get_by_test_id("add-device-dialog").wait_for(state="visible")
        page.get_by_test_id("device-tab-remote").click()
        page.get_by_test_id("remote-server-url").fill(mock_agent_server)
        page.get_by_test_id("discover-remote-devices").click()
        page.get_by_test_id("remote-device-option-mock_device_001").wait_for(
            state="visible"
        )
        page.get_by_test_id("remote-device-option-mock_device_001").click()
        page.get_by_test_id("connect-remote-device").click()
        page.get_by_test_id("add-device-dialog").wait_for(state="hidden")

        # Submit the task from the chat UI.
        page.get_by_test_id("chat-input").wait_for(state="visible", timeout=15000)
        page.get_by_test_id("chat-input").fill("点击屏幕下方的消息按钮")
        page.get_by_test_id("chat-send").click()

        final_message = page.get_by_test_id("assistant-message-final").last
        final_message.wait_for(state="visible", timeout=120000)
        assert "已成功点击消息按钮" in (final_message.text_content() or "")

        # Verify the same backend side effects as the API-level local E2E test.
        mock_llm_stats = mock_llm_client.get_stats()
        assert mock_llm_stats["request_count"] == 2, (
            f"Expected 2 LLM requests, got {mock_llm_stats['request_count']}"
        )

        commands = test_client.get_commands()
        tap_commands = [command for command in commands if command["action"] == "tap"]
        assert len(tap_commands) >= 1, (
            f"Expected at least 1 tap, got {len(tap_commands)}. All commands: {commands}"
        )

        tap = tap_commands[0]
        x, y = tap["params"]["x"], tap["params"]["y"]
        assert 487 <= x <= 721, f"Tap x={x} not in message button region [487, 721]"
        assert 2516 <= y <= 2667, f"Tap y={y} not in message button region [2516, 2667]"

        state = test_client.get_state()
        assert state["current_state"] == "message", (
            f"Expected state 'message', got '{state['current_state']}'"
        )
