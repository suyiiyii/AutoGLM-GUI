"""MAI Agent adapter for AutoGLM-GUI.

This module provides an adapter that wraps mai_agent.MAIUINaivigationAgent
to make it compatible with the PhoneAgent interface used in AutoGLM-GUI.
"""

from __future__ import annotations

import base64
import re
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

from PIL import Image

from phone_agent.actions.handler import ActionHandler
from phone_agent.agent import AgentConfig, StepResult
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelConfig

from AutoGLM_GUI.logger import logger


# Add mai_agent to sys.path for import
# mai_agent uses top-level imports (e.g., "from base import BaseAgent")
# which require the mai_agent directory to be in Python path
def _ensure_mai_agent_importable() -> None:
    """Ensure mai_agent directory is in sys.path for importing.

    This function handles multiple environments:
    - Development: mai_agent is in project root
    - Wheel installation: mai_agent is installed as data file
    - PyInstaller: mai_agent is in sys._MEIPASS
    """
    # Check if already importable
    try:
        import mai_naivigation_agent  # noqa: F401

        return
    except ImportError:
        pass

    # Try to locate mai_agent directory
    mai_agent_paths = []

    # 1. PyInstaller environment: check sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        mai_agent_paths.append(meipass / "mai_agent")

    # 2. Wheel installation: check site-packages
    # Try to get the package location
    try:
        import AutoGLM_GUI

        pkg_root = Path(AutoGLM_GUI.__file__).parent.parent
        mai_agent_paths.append(pkg_root / "mai_agent")
    except (ImportError, AttributeError):
        pass

    # 3. Development environment: check project root relative to this file
    # This file is at: AutoGLM_GUI/agents/mai_adapter.py
    # Project root is 3 levels up
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent
    mai_agent_paths.append(project_root / "mai_agent")

    # Add first existing path to sys.path
    for mai_path in mai_agent_paths:
        if mai_path.exists() and mai_path.is_dir():
            mai_path_str = str(mai_path)
            if mai_path_str not in sys.path:
                sys.path.insert(0, mai_path_str)
                logger.debug(f"Added {mai_path_str} to sys.path for mai_agent imports")
            return

    # If we get here, mai_agent was not found
    logger.warning(
        "mai_agent directory not found. MAI Agent functionality may not work."
    )


_ensure_mai_agent_importable()

if TYPE_CHECKING:
    from mai_naivigation_agent import MAIUINaivigationAgent


@dataclass
class MAIAgentConfig:
    """MAI Agent specific configuration.

    Attributes:
        history_n: Number of historical screenshots to include in context.
        max_pixels: Maximum pixels for image resizing (optional).
        min_pixels: Minimum pixels for image resizing (optional).
        tools: MCP tools list (optional, not implemented yet).
        use_mai_prompt: Whether to use MAI's native prompt format.
    """

    history_n: int = 3
    max_pixels: Optional[int] = None
    min_pixels: Optional[int] = None
    tools: Optional[list[dict[str, Any]]] = None
    use_mai_prompt: bool = False


class MAIAgentAdapter:
    """
    Adapter for MAI Agent that implements PhoneAgent-compatible interface.

    This adapter wraps mai_agent.MAIUINaivigationAgent and provides:
    - Compatible run() and step() methods
    - Action format conversion (MAI → PhoneAgent)
    - Coordinate system conversion (0-999 → 0-1000)
    - Reuses existing ActionHandler for ADB operations
    - Trajectory management via MAI's TrajMemory

    Example:
        >>> adapter = MAIAgentAdapter(model_config, agent_config, mai_config)
        >>> result = adapter.run("Open Settings")
        >>> print(result)
    """

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        mai_config: MAIAgentConfig,
        confirmation_callback: Optional[Callable[[str], bool]] = None,
        takeover_callback: Optional[Callable[[str], None]] = None,
        on_thinking_chunk: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the MAI Agent adapter.

        Args:
            model_config: Model configuration (base_url, model_name, etc.)
            agent_config: Agent configuration (device_id, max_steps, etc.)
            mai_config: MAI-specific configuration
            confirmation_callback: Callback for sensitive action confirmation
            takeover_callback: Callback for takeover requests
            on_thinking_chunk: Callback for streaming thinking chunks
        """
        self.model_config = model_config
        self.agent_config = agent_config
        self.mai_config = mai_config

        # Import and create MAI agent
        # Note: We import from mai_naivigation_agent directly (not mai_agent.mai_naivigation_agent)
        # because we've added the mai_agent directory to sys.path
        from mai_naivigation_agent import MAIUINaivigationAgent

        runtime_conf = {
            "history_n": mai_config.history_n,
            "temperature": model_config.temperature,
            "top_k": -1,  # MAI default
            "top_p": model_config.top_p,
            "max_tokens": model_config.max_tokens,
        }

        if mai_config.max_pixels:
            runtime_conf["max_pixels"] = mai_config.max_pixels
        if mai_config.min_pixels:
            runtime_conf["min_pixels"] = mai_config.min_pixels

        self.mai_agent: MAIUINaivigationAgent = MAIUINaivigationAgent(
            llm_base_url=model_config.base_url,
            model_name=model_config.model_name,
            runtime_conf=runtime_conf,
            tools=mai_config.tools,
        )

        # Create action handler (reuse from phone_agent)
        self.action_handler = ActionHandler(
            device_id=agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        # State management
        self._step_count = 0
        self._current_instruction = ""
        self._on_thinking_chunk = on_thinking_chunk

        logger.info(
            f"MAI Agent adapter initialized for device {agent_config.device_id} "
            f"using model {model_config.model_name}"
        )

    def run(self, task: str) -> str:
        """Run the agent to complete a task.

        This method loops through steps until the task is finished
        or max_steps is reached.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self._current_instruction = task
        self.mai_agent.reset()
        self._step_count = 0

        while self._step_count < self.agent_config.max_steps:
            result = self._execute_step(is_first=(self._step_count == 0))

            if result.finished:
                return result.message or "Task completed"

            self._step_count += 1

        return "Max steps reached"

    def step(self, task: Optional[str] = None) -> StepResult:
        """Execute a single step.

        Args:
            task: Task description (only required for the first step).

        Returns:
            StepResult containing the action and thinking.
        """
        is_first = self._step_count == 0

        if is_first:
            if not task:
                raise ValueError("Task is required for the first step")
            self._current_instruction = task
            if len(self.mai_agent.traj_memory.steps) == 0:
                self.mai_agent.reset()

        result = self._execute_step(is_first=is_first)
        self._step_count += 1
        return result

    def reset(self) -> None:
        """Reset the agent state."""
        self.mai_agent.reset()
        self._step_count = 0
        self._current_instruction = ""

    def _execute_step(self, is_first: bool) -> StepResult:
        """Execute a single step (internal method).

        Args:
            is_first: Whether this is the first step.

        Returns:
            StepResult
        """
        # 1. Get current screenshot
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)

        # 2. Convert base64_data to PIL Image
        # The Screenshot object contains base64_data, not pil_image
        image_data = base64.b64decode(screenshot.base64_data)
        pil_image = Image.open(BytesIO(image_data))

        # 3. Build observation dictionary
        obs = {
            "screenshot": pil_image,
            "accessibility_tree": None,  # Not supported yet
        }

        # 4. Call MAI agent predict
        # IMPORTANT: Always pass self._current_instruction, not just on the first step.
        # MAI agent's _build_messages uses instruction to populate the primary user message,
        # and does not re-inject it from history. Without the instruction in subsequent steps,
        # the model would lose track of the task goal as history grows.
        try:
            prediction_text, action_dict = self.mai_agent.predict(
                instruction=self._current_instruction,
                obs=obs,
            )
        except Exception as e:
            logger.error(f"MAI agent prediction failed: {e}")
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Prediction error: {e}",
            )

        # 5. Extract thinking from prediction_text
        # MAI Agent uses <thinking> tags
        thinking = self._extract_thinking(prediction_text)

        # 6. Convert action format
        converted_action = self._convert_action(action_dict)

        # 7. Execute action
        try:
            action_result = self.action_handler.execute(
                converted_action,
                screenshot.width,
                screenshot.height,
            )
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return StepResult(
                success=False,
                finished=True,
                action=converted_action,
                thinking=thinking,
                message=f"Action error: {e}",
            )

        # 8. Check if finished
        finished = (
            converted_action.get("_metadata") == "finish" or action_result.should_finish
        )

        return StepResult(
            success=action_result.success,
            finished=finished,
            action=converted_action,
            thinking=thinking,
            message=action_result.message,
        )

    def _convert_action(self, mai_action: dict[str, Any]) -> dict[str, Any]:
        """Convert MAI action format to PhoneAgent format.

        MAI format: {"action": "click", "coordinate": [x, y]}
        PhoneAgent format: {"_metadata": "do", "action": "Tap", "element": [x, y]}

        Coordinate conversion: MAI uses 0-999, PhoneAgent uses 0-1000.

        Args:
            mai_action: Action dictionary from MAI agent.

        Returns:
            Converted action dictionary for PhoneAgent.
        """
        action_type = mai_action.get("action")

        # Terminate action
        if action_type == "terminate":
            status = mai_action.get("status", "success")
            return {
                "_metadata": "finish",
                "message": "Task completed" if status == "success" else "Task failed",
            }

        # Answer action (no operation)
        if action_type == "answer":
            return {
                "_metadata": "finish",
                "message": mai_action.get("text", ""),
            }

        # Wait action
        if action_type == "wait":
            return {
                "_metadata": "do",
                "action": "Wait",
                "duration": "1 seconds",
            }

        # System button
        if action_type == "system_button":
            button_name = mai_action.get("button", "")

            # Special handling for Enter key
            # ActionHandler doesn't have an "Enter" handler, so we handle it directly here
            if button_name == "enter":
                # Use platform_utils to run ADB keyevent command
                from AutoGLM_GUI.platform_utils import run_cmd_silently_sync

                adb_prefix = (
                    ["adb", "-s", self.agent_config.device_id]
                    if self.agent_config.device_id
                    else ["adb"]
                )
                run_cmd_silently_sync(
                    adb_prefix + ["shell", "input", "keyevent", "KEYCODE_ENTER"],
                    timeout=5,
                )
                # Return a Wait action to indicate success
                return {
                    "_metadata": "do",
                    "action": "Wait",
                    "duration": "0.5 seconds",
                }

            # Other system buttons use standard handlers
            action_map = {
                "back": "Back",
                "home": "Home",
            }
            return {
                "_metadata": "do",
                "action": action_map.get(button_name, "Back"),
            }

        # Click-type actions (require coordinates)
        coordinate = mai_action.get("coordinate")
        if coordinate:
            # Coordinate conversion: 0-999 -> 0-1000
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

        # Swipe action
        if action_type == "swipe":
            direction = mai_action.get("direction", "up")
            # Default to normalized center [0.5, 0.5], not [500, 500]
            # MAI coordinates are normalized to [0, 1], so we use normalized values
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

        # Drag action
        if action_type == "drag":
            start_coord = mai_action.get("start_coordinate", [0, 0])
            end_coord = mai_action.get("end_coordinate", [0, 0])

            # IMPORTANT: start_coordinate and end_coordinate are NOT normalized by MAI.
            # They remain in SCALE_FACTOR range [0, 999], unlike the "coordinate" field
            # which is normalized to [0, 1]. We must use the scale factor conversion.
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

        # Text input
        if action_type == "type":
            return {
                "_metadata": "do",
                "action": "Type",
                "text": mai_action.get("text", ""),
            }

        # Open app
        if action_type == "open":
            return {
                "_metadata": "do",
                "action": "Launch",
                "app": mai_action.get("text", ""),
            }

        # Unknown action - treat as finish
        logger.warning(f"Unknown MAI action type: {action_type}")
        return {
            "_metadata": "finish",
            "message": f"Unknown action: {action_type}",
        }

    def _convert_coordinate(self, coord: float) -> int:
        """Convert coordinate from MAI scale to PhoneAgent scale.

        MAI agent normalizes coordinates to [0, 1] in parse_action_to_structure_output.
        PhoneAgent uses normalized coordinates in [0, 1000] range.

        Args:
            coord: Coordinate in MAI scale [0, 1] (normalized).

        Returns:
            Coordinate in PhoneAgent scale [0, 1000].

        Example:
            >>> _convert_coordinate(0.5)  # Center of screen
            500
        """
        return int(coord * 1000)

    def _convert_coordinate_from_scale_factor(self, coord: float) -> int:
        """Convert coordinate from MAI SCALE_FACTOR to PhoneAgent scale.

        For drag actions, MAI does NOT normalize start_coordinate/end_coordinate.
        These coordinates remain in the SCALE_FACTOR range [0, 999].
        PhoneAgent uses normalized coordinates in [0, 1000] range.

        Args:
            coord: Coordinate in MAI SCALE_FACTOR [0, 999].

        Returns:
            Coordinate in PhoneAgent scale [0, 1000].

        Example:
            >>> _convert_coordinate_from_scale_factor(500)  # Center of screen
            500
        """
        SCALE_FACTOR = 999
        return int(coord * 1000 / SCALE_FACTOR)

    def _calculate_swipe_coordinates(
        self, direction: str, x: int, y: int
    ) -> Tuple[list[int], list[int]]:
        """Calculate swipe coordinates based on direction.

        Args:
            direction: Swipe direction (up, down, left, right).
            x: Center X coordinate.
            y: Center Y coordinate.

        Returns:
            Tuple of [start_x, start_y] and [end_x, end_y].
        """
        distance = 300  # Default swipe distance

        if direction == "up":
            start = [x, y + distance // 2]
            end = [x, y - distance // 2]
        elif direction == "down":
            start = [x, y - distance // 2]
            end = [x, y + distance // 2]
        elif direction == "left":
            start = [x + distance // 2, y]
            end = [x - distance // 2, y]
        elif direction == "right":
            start = [x - distance // 2, y]
            end = [x + distance // 2, y]
        else:
            start = [x, y]
            end = [x, y]

        return start, end

    def _extract_thinking(self, prediction_text: str) -> str:
        """Extract thinking content from agent response.

        MAI Agent format:
        <thinking>reasoning process</thinking>
        <tool_call>...</tool_call>

        GLM Agent format:
        ```
        详细的推理过程...
        ```
        <answer>action</answer>

        Args:
            prediction_text: Full prediction text from agent.

        Returns:
            Thinking content (empty string if not found or truncated).
        """
        # Try <thinking> tags first (MAI Agent format)
        match = re.search(r"<thinking>(.*?)</thinking>", prediction_text, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            # Truncate if too long (MAI Agent can produce very long reasoning)
            if len(thinking) > 500:
                thinking = thinking[:500] + "..."
            return thinking

        # Fallback to ``` tags (GLM format)
        match = re.search(r"```(.*?)```", prediction_text, re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            if len(thinking) > 500:
                thinking = thinking[:500] + "..."
            return thinking

        return ""

    @property
    def context(self) -> list[dict[str, Any]]:
        """Return trajectory history in PhoneAgent format (read-only).

        This property converts MAI's TrajMemory to PhoneAgent's context format.

        Returns:
            List of message dictionaries.
        """
        context = []

        for step in self.mai_agent.traj_memory.steps:
            # Assistant message
            if step.thought:
                content = f"<thinking>\n{step.thought}\n</thinking>\n<answer>\n{step.action}\n</answer>"
                context.append(
                    {
                        "role": "assistant",
                        "content": content,
                    }
                )

        return context

    @property
    def step_count(self) -> int:
        """Return current step count."""
        return self._step_count
