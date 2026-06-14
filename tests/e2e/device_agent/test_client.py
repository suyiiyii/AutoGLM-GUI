"""Test client for Mock Device Agent.

Provides a convenient API for interacting with the Mock Device Agent
in integration tests.
"""

import httpx


class MockAgentTestClient:
    """
    Test client for Mock Device Agent.

    Example:
        >>> client = MockAgentTestClient("http://localhost:8001")
        >>> client.reset()
        >>> client.load_scenario("scenarios/meituan_message/scenario.yaml")
        >>>
        >>> # ... run your test (AutoGLM-GUI sends commands to mock agent) ...
        >>>
        >>> commands = client.get_commands()
        >>> assert len(commands) > 0
        >>> assert commands[0]["action"] == "tap"
    """

    def __init__(self, base_url: str = "http://localhost:8001", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def reset(self) -> None:
        """Reset command history."""
        self._client.post("/test/reset")

    def load_scenario(self, scenario_path: str) -> dict:
        """Load a test scenario."""
        resp = self._client.post(
            "/test/load_scenario", json={"scenario_path": scenario_path}
        )
        resp.raise_for_status()
        return resp.json()

    def get_commands(self) -> list[dict]:
        """Get all recorded commands."""
        resp = self._client.get("/test/commands")
        return resp.json()

    def get_actions(self) -> list[dict]:
        """Get simplified action list (action + params only)."""
        resp = self._client.get("/test/commands/actions")
        return resp.json()

    def get_state(self) -> dict:
        """Get current state machine state."""
        resp = self._client.get("/test/state")
        return resp.json()

    def expect(self, actions: list[str]) -> dict:
        """
        Verify expected command sequence.

        Args:
            actions: List of expected action names.

        Returns:
            Match result with details.
        """
        resp = self._client.get("/test/expect", params={"actions": ",".join(actions)})
        return resp.json()

    def assert_actions(self, expected: list[str]) -> None:
        """
        Assert that recorded actions match expected sequence.

        Args:
            expected: List of expected action names.

        Raises:
            AssertionError: If actions don't match.
        """
        result = self.expect(expected)
        assert result["match"], result["message"]

    def assert_tap_in_region(
        self, x1: int, y1: int, x2: int, y2: int, index: int = 0
    ) -> None:
        """
        Assert that a tap command was in the specified region.

        Args:
            x1, y1, x2, y2: Region bounds.
            index: Index of tap command to check (default: first tap).

        Raises:
            AssertionError: If tap not in region.
        """
        actions = self.get_actions()
        taps = [a for a in actions if a["action"] == "tap"]

        assert len(taps) > index, (
            f"Expected at least {index + 1} tap(s), got {len(taps)}"
        )

        tap = taps[index]
        x, y = tap["x"], tap["y"]

        assert x1 <= x <= x2, f"Tap x={x} not in range [{x1}, {x2}]"
        assert y1 <= y <= y2, f"Tap y={y} not in range [{y1}, {y2}]"

    def assert_state(self, expected_state: str) -> None:
        """
        Assert current state machine state.

        Args:
            expected_state: Expected state ID.

        Raises:
            AssertionError: If state doesn't match.
        """
        state = self.get_state()
        assert state["current_state"] == expected_state, (
            f"Expected state '{expected_state}', got '{state['current_state']}'"
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
