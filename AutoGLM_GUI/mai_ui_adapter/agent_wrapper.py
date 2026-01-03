"""MAI-UI PhoneAgent wrapper for compatibility with AutoGLM-GUI interface."""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from phone_agent.agent import AgentConfig, StepResult
from phone_agent.actions.handler import ActionHandler
from phone_agent.model import ModelConfig

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.mai_ui.mai_navigation_agent import MAIUINaivigationAgent  # type: ignore[import-not-found]
from AutoGLM_GUI.mai_ui_adapter.action_adapter import MAIUIActionAdapter  # type: ignore[import-not-found]


@dataclass
class MAIUIConfig:
    """MAI-UI specific configuration."""

    history_n: int = 3
    temperature: float = 0.0
    top_k: int = -1
    top_p: float = 1.0
    max_tokens: int = 2048


class MAIUIPhoneAgent:
    """
    MAI-UI Agent wrapper that implements the PhoneAgent interface.

    This wrapper allows MAI-UI agents to be used transparently in place of
    the standard PhoneAgent, providing compatibility with the existing
    PhoneAgentManager and API infrastructure.

    Usage:
        agent = MAIUIPhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )
        result = agent.run("Open WeChat")
    """

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        mai_config: Optional[MAIUIConfig] = None,
        takeover_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize MAI-UI PhoneAgent wrapper.

        Args:
            model_config: Model configuration (base_url, api_key, model_name).
            agent_config: Agent configuration (device_id, max_steps, etc.).
            mai_config: MAI-UI specific configuration.
            takeover_callback: Callback for takeover requests.
        """
        self.model_config = model_config
        self.agent_config = agent_config
        self.mai_config = mai_config or MAIUIConfig()

        # Create MAI-UI navigation agent
        self._mai_agent = MAIUINaivigationAgent(
            llm_base_url=model_config.base_url,
            model_name=model_config.model_name,
            api_key=model_config.api_key,
            runtime_conf={
                "history_n": self.mai_config.history_n,
                "temperature": self.mai_config.temperature,
                "top_k": self.mai_config.top_k,
                "top_p": self.mai_config.top_p,
                "max_tokens": self.mai_config.max_tokens,
            },
        )

        # Action adapter and handler
        self._action_adapter = MAIUIActionAdapter()
        self.action_handler = ActionHandler(
            device_id=agent_config.device_id,
            takeover_callback=takeover_callback,
        )

        # PhoneAgent-compatible state
        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._current_task: str = ""

        # For model_client compatibility (used by streaming patches)
        self.model_client = _DummyModelClient()

        # Debug: Print model configuration for troubleshooting
        logger.info("=" * 60)
        logger.info("[MAI-UI Agent] Initialization")
        logger.info(f"  Device ID: {agent_config.device_id}")
        logger.info(f"  Base URL:  {model_config.base_url}")
        logger.info(f"  Model:     {model_config.model_name}")
        logger.info("=" * 60)

    def run(self, task: str) -> str:
        """
        Execute a complete task.

        Args:
            task: Natural language task description.

        Returns:
            Final message from the agent.
        """
        self.reset()
        self._current_task = task

        # First step
        result = self._execute_step(task, is_first=True)

        if result.finished:
            return result.message or "Task completed"

        # Continue until finished or max steps reached
        while self._step_count < self.agent_config.max_steps:
            result = self._execute_step(is_first=False)

            if result.finished:
                return result.message or "Task completed"

        return "Max steps reached"

    def step(self, task: Optional[str] = None) -> StepResult:
        """
        Execute a single step.

        Args:
            task: Task description (required for first step).

        Returns:
            StepResult with step details.
        """
        is_first = len(self._context) == 0

        if is_first:
            if not task:
                raise ValueError("Task is required for the first step")
            self._current_task = task

        return self._execute_step(task, is_first)

    def _execute_step(
        self, user_prompt: Optional[str] = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        from phone_agent.device_factory import get_device_factory
        from PIL import Image
        from io import BytesIO

        self._step_count += 1
        logger.info(f"[MAI-UI] Executing step {self._step_count}")

        # Get screenshot
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)

        # Convert base64 to PIL Image
        import base64

        image_bytes = base64.b64decode(screenshot.base64_data)
        pil_image = Image.open(BytesIO(image_bytes))

        # Build observation
        obs = {
            "screenshot": pil_image,
            "accessibility_tree": None,
        }

        # Get instruction
        instruction = user_prompt or self._current_task

        # Call MAI-UI predict
        try:
            raw_response, action_json = self._mai_agent.predict(
                instruction=instruction,
                obs=obs,
            )
        except Exception as e:
            logger.error(f"[MAI-UI] Predict failed: {e}")
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Prediction failed: {e}",
            )

        # Check for error
        if action_json.get("action") is None:
            logger.error("[MAI-UI] Invalid action returned")
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message="Invalid action from model",
            )

        # Get thinking from trajectory
        thinking = ""
        if self._mai_agent.traj_memory.steps:
            last_step = self._mai_agent.traj_memory.steps[-1]
            thinking = last_step.thought or ""

        # Convert action to AutoGLM-GUI format
        converted_action = self._action_adapter.convert(action_json)
        logger.debug(f"[MAI-UI] Converted action: {converted_action}")

        # Check if finished (terminate action)
        if converted_action.get("_metadata") == "finish":
            return StepResult(
                success=True,
                finished=True,
                action=converted_action,
                thinking=thinking,
                message=converted_action.get("message", "Task completed"),
            )

        # Execute action
        try:
            result = self.action_handler.execute(
                converted_action,
                screenshot.width,
                screenshot.height,
            )
        except Exception as e:
            logger.error(f"[MAI-UI] Action execution failed: {e}")
            return StepResult(
                success=False,
                finished=False,
                action=converted_action,
                thinking=thinking,
                message=f"Action failed: {e}",
            )

        # Update context for compatibility
        self._context.append(
            {
                "step": self._step_count,
                "action": action_json,
                "converted_action": converted_action,
                "result": result.success,
                "thinking": thinking,
            }
        )

        return StepResult(
            success=result.success,
            finished=result.should_finish,
            action=converted_action,
            thinking=thinking,
            message=result.message,
        )

    def reset(self) -> None:
        """Reset agent state for a new task."""
        self._context = []
        self._step_count = 0
        self._current_task = ""
        self._mai_agent.reset()
        logger.debug("[MAI-UI] Agent reset")

    @property
    def step_count(self) -> int:
        """Get current step count."""
        return self._step_count

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get conversation context (for compatibility)."""
        return self._context.copy()


class _DummyModelClient:
    """
    Dummy model client for compatibility with streaming patches.

    The actual model calls are handled by MAI-UI agent internally.
    This exists to satisfy code that expects model_client attribute.
    """

    def request(self, messages: list, **kwargs) -> Any:
        """Dummy request method - should not be called directly."""
        raise NotImplementedError(
            "MAIUIPhoneAgent handles model calls internally. "
            "Do not call model_client.request() directly."
        )
