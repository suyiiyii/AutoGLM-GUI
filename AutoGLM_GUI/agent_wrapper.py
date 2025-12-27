"""Wrapper for PhoneAgent to support interruption."""

import threading
from typing import Any, Callable

from AutoGLM_GUI.exceptions import TaskInterruptedError
from AutoGLM_GUI.logger import logger
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig


class WrappedModelClient:
    """Wrapper for ModelClient to check for interruption before requests."""

    def __init__(self, original_client: Any, interrupt_check: Callable[[], bool]):
        self._client = original_client
        self._check = interrupt_check

    def request(self, *args, **kwargs) -> Any:
        if self._check():
            logger.info("ModelClient request interrupted")
            raise TaskInterruptedError()
        return self._client.request(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class WrappedActionHandler:
    """Wrapper for ActionHandler to check for interruption before actions."""

    def __init__(self, original_handler: Any, interrupt_check: Callable[[], bool]):
        self._handler = original_handler
        self._check = interrupt_check

    def execute(self, *args, **kwargs) -> Any:
        if self._check():
            logger.info("ActionHandler execution interrupted")
            raise TaskInterruptedError()
        return self._handler.execute(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._handler, name)


class InterruptiblePhoneAgent(PhoneAgent):
    """
    A PhoneAgent subclass that supports interruption.

    It wraps model_client and action_handler to check for an interruption flag.
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        super().__init__(
            model_config=model_config,
            agent_config=agent_config,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )
        self._interrupt_event = threading.Event()

        # Wrap components to intercept calls
        self.model_client = WrappedModelClient(
            self.model_client, lambda: self._interrupt_event.is_set()
        )
        self.action_handler = WrappedActionHandler(
            self.action_handler, lambda: self._interrupt_event.is_set()
        )

    def interrupt(self) -> None:
        """Interrupt the current task."""
        logger.info(f"Interrupting agent for device {self.agent_config.device_id}")
        self._interrupt_event.set()

    @property
    def interrupted(self) -> bool:
        """Check if the agent has been interrupted."""
        return self._interrupt_event.is_set()

    def reset(self) -> None:
        """Reset the agent state, including interruption flag."""
        self._interrupt_event.clear()
        super().reset()
