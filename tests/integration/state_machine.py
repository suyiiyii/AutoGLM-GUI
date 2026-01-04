"""State machine for Agent integration testing.

This module provides the core state machine that manages test states
and transitions based on Agent actions.
"""

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Transition:
    """Defines a state transition triggered by clicking a region."""

    click_region: tuple[int, int, int, int]  # (x1, y1, x2, y2)
    next_state: str
    description: str = ""  # Optional description for logging

    def contains_point(self, x: int, y: int) -> bool:
        """Check if a point is within this click region.

        Note: The click_region should already include any desired tolerance
        in its boundary definition (x1, y1, x2, y2).
        """
        x1, y1, x2, y2 = self.click_region
        return x1 <= x <= x2 and y1 <= y <= y2


@dataclass
class TestState:
    """Represents a single state in the test state machine."""

    id: str
    screenshot_path: Path
    current_app: str = "com.android.launcher"
    transitions: list[Transition] = field(default_factory=list)
    is_terminal: bool = False
    expected_finish: bool = False

    # Cached screenshot data
    _screenshot_base64: str | None = None
    _screenshot_width: int | None = None
    _screenshot_height: int | None = None

    def load_screenshot(self) -> tuple[str, int, int]:
        """Load and cache screenshot data.

        Returns:
            Tuple of (base64_data, width, height)
        """
        if self._screenshot_base64 is None:
            from io import BytesIO

            from PIL import Image

            img = Image.open(self.screenshot_path)
            self._screenshot_width, self._screenshot_height = img.size

            buffered = BytesIO()
            img.save(buffered, format="PNG")
            self._screenshot_base64 = base64.b64encode(buffered.getvalue()).decode(
                "utf-8"
            )

        assert (
            self._screenshot_width is not None and self._screenshot_height is not None
        )
        return self._screenshot_base64, self._screenshot_width, self._screenshot_height


@dataclass
class ScreenshotResult:
    """Mimics the screenshot result from real device."""

    base64_data: str
    width: int
    height: int


class StateMachine:
    """
    Manages test state transitions based on Agent actions.

    The state machine tracks the current state and handles transitions
    when the Agent performs actions that match defined click regions.
    """

    def __init__(
        self,
        states: dict[str, TestState],
        initial_state: str,
        max_retries_per_transition: int = 3,
    ):
        """
        Initialize the state machine.

        Args:
            states: Dictionary of state_id -> TestState
            initial_state: ID of the initial state
            max_retries_per_transition: Max retries for each transition
        """
        self.states = states
        self.initial_state = initial_state
        self.current_state_id = initial_state
        self.max_retries = max_retries_per_transition

        # Track retries and history
        self.retry_count = 0
        self.action_history: list[dict[str, Any]] = []
        self.state_history: list[str] = [initial_state]

        # Test result tracking
        self.test_passed = False
        self.failure_reason: str | None = None

    @property
    def current_state(self) -> TestState:
        """Get the current state."""
        return self.states[self.current_state_id]

    def get_current_screenshot(self) -> ScreenshotResult:
        """Get screenshot for the current state."""
        base64_data, width, height = self.current_state.load_screenshot()
        return ScreenshotResult(
            base64_data=base64_data,
            width=width,
            height=height,
        )

    def handle_tap(self, x: int, y: int) -> bool:
        """
        Handle a tap action from the Agent.

        Args:
            x: X coordinate of tap
            y: Y coordinate of tap

        Returns:
            True if transition occurred, False otherwise

        Raises:
            TestFailedError: If max retries exceeded
        """
        self.action_history.append(
            {
                "action": "tap",
                "x": x,
                "y": y,
                "state": self.current_state_id,
            }
        )

        # Check if we're in a terminal state
        if self.current_state.is_terminal:
            return True

        # Check all transitions for the current state
        for transition in self.current_state.transitions:
            if transition.contains_point(x, y):
                # Successful transition
                self.retry_count = 0
                old_state = self.current_state_id
                self.current_state_id = transition.next_state
                self.state_history.append(self.current_state_id)
                print(
                    f"[StateMachine] Transition: {old_state} -> {self.current_state_id} "
                    f"(tap at {x}, {y})"
                )
                return True

        # Tap missed all regions
        self.retry_count += 1
        print(
            f"[StateMachine] Tap missed ({x}, {y}) in state {self.current_state_id}, "
            f"retry {self.retry_count}/{self.max_retries}"
        )

        if self.retry_count >= self.max_retries:
            self.failure_reason = (
                f"Max retries ({self.max_retries}) exceeded in state "
                f"'{self.current_state_id}'. Last tap at ({x}, {y}). "
                f"Expected regions: {[t.click_region for t in self.current_state.transitions]}"
            )
            raise TestFailedError(self.failure_reason)

        return False

    def handle_swipe(self, start_x: int, start_y: int, end_x: int, end_y: int) -> bool:
        """Handle a swipe action (currently just logs it)."""
        self.action_history.append(
            {
                "action": "swipe",
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "state": self.current_state_id,
            }
        )
        # Swipe doesn't trigger transitions in basic implementation
        return False

    def handle_finish(self, message: str | None = None) -> None:
        """Handle Agent finish action."""
        self.action_history.append(
            {
                "action": "finish",
                "message": message,
                "state": self.current_state_id,
            }
        )

        # Check if we're in a terminal state that expects finish
        if self.current_state.is_terminal and self.current_state.expected_finish:
            self.test_passed = True
            print(f"[StateMachine] Test PASSED! Final state: {self.current_state_id}")
        else:
            self.failure_reason = (
                f"Agent finished in non-terminal state '{self.current_state_id}'"
            )
            print(f"[StateMachine] Test FAILED: {self.failure_reason}")

    def is_complete(self) -> bool:
        """Check if the test is complete (reached terminal state or failed)."""
        return self.current_state.is_terminal or self.failure_reason is not None

    def get_result(self) -> dict[str, Any]:
        """Get test result summary."""
        return {
            "passed": self.test_passed,
            "failure_reason": self.failure_reason,
            "final_state": self.current_state_id,
            "state_history": self.state_history,
            "action_count": len(self.action_history),
            "action_history": self.action_history,
        }


class TestFailedError(Exception):
    """Raised when a test fails due to max retries or other errors."""

    pass


def load_test_case(
    yaml_path: str | Path, base_dir: str | Path | None = None
) -> tuple[StateMachine, str, int]:
    """
    Load a test case from YAML file.

    Args:
        yaml_path: Path to the YAML test case file
        base_dir: Base directory for resolving screenshot paths (defaults to YAML dir)

    Returns:
        Tuple of (StateMachine, instruction, max_steps)

    Raises:
        ValueError: If YAML validation fails
    """
    import yaml
    from tests.integration.schema import TestScenarioSchema

    yaml_path = Path(yaml_path)
    base_dir = Path(base_dir) if base_dir else yaml_path.parent

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    # Validate YAML data against schema
    try:
        TestScenarioSchema.model_validate(data)
    except Exception as e:
        raise ValueError(f"Invalid test scenario YAML: {e}") from e

    # Parse states (use validated data)
    states: dict[str, TestState] = {}
    initial_state: str | None = None

    for state_data in data["states"]:
        state_id = state_data["id"]

        # Resolve screenshot path
        screenshot_path = base_dir / state_data["screenshot"]

        # Parse transitions
        transitions = []
        for trans_data in state_data.get("transitions", []):
            transitions.append(
                Transition(
                    click_region=tuple(trans_data["click_region"]),
                    next_state=trans_data["next_state"],
                    description=trans_data.get("description", ""),
                )
            )

        state = TestState(
            id=state_id,
            screenshot_path=screenshot_path,
            current_app=state_data.get("current_app", "com.android.launcher"),
            transitions=transitions,
            is_terminal=state_data.get("is_terminal", False),
            expected_finish=state_data.get("expected_finish", False),
        )
        states[state_id] = state

        # First state is initial
        if initial_state is None:
            initial_state = state_id

    if initial_state is None:
        raise ValueError("No states defined in test case")

    state_machine = StateMachine(states, initial_state)

    return (
        state_machine,
        data["instruction"],
        data.get("max_steps", 10),
    )
