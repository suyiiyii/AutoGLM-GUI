"""PhoneAgent lifecycle and concurrency manager (singleton)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional

from AutoGLM_GUI.exceptions import (
    AgentInitializationError,
    AgentNotInitializedError,
    DeviceBusyError,
)
from AutoGLM_GUI.logger import logger

if TYPE_CHECKING:
    from phone_agent import PhoneAgent
    from phone_agent.agent import AgentConfig
    from phone_agent.model import ModelConfig


class AgentState(str, Enum):
    """Agent runtime state."""

    IDLE = "idle"  # Agent initialized, not processing
    BUSY = "busy"  # Agent processing a request
    ERROR = "error"  # Agent encountered error
    INITIALIZING = "initializing"  # Agent being created


@dataclass
class AgentMetadata:
    """Metadata for a PhoneAgent instance."""

    device_id: str
    state: AgentState
    model_config: ModelConfig
    agent_config: AgentConfig
    created_at: float
    last_used: float
    error_message: Optional[str] = None


class PhoneAgentManager:
    """
    Singleton manager for PhoneAgent lifecycle and concurrency control.

    Features:
    - Thread-safe agent creation/destruction
    - Per-device locking (device-level concurrency control)
    - State management (IDLE/BUSY/ERROR/INITIALIZING)
    - Integration with DeviceManager
    - Configuration hot-reload support
    - Connection switching detection

    Design Principles:
    - Uses state.agents and state.agent_configs as storage (backward compatible)
    - Double-checked locking for device locks
    - RLock for manager-level operations (supports reentrant calls)
    - Context managers for automatic lock release

    Example:
        >>> manager = PhoneAgentManager.get_instance()
        >>>
        >>> # Initialize agent
        >>> agent = manager.initialize_agent(device_id, model_config, agent_config)
        >>>
        >>> # Use agent with automatic locking
        >>> with manager.use_agent(device_id) as agent:
        >>>     result = agent.run("Open WeChat")
    """

    _instance: Optional[PhoneAgentManager] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        """Private constructor. Use get_instance() instead."""
        # Manager-level lock (protects internal state)
        self._manager_lock = threading.RLock()

        # Device-level locks (per-device concurrency control)
        self._device_locks: dict[str, threading.Lock] = {}
        self._device_locks_lock = threading.Lock()

        # Agent metadata (indexed by device_id)
        self._metadata: dict[str, AgentMetadata] = {}

        # State tracking
        self._states: dict[str, AgentState] = {}

    @classmethod
    def get_instance(cls) -> PhoneAgentManager:
        """Get singleton instance (thread-safe, double-checked locking)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
                    logger.info("PhoneAgentManager singleton created")
        return cls._instance

    # ==================== Agent Lifecycle ====================

    def initialize_agent(
        self,
        device_id: str,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        takeover_callback: Optional[Callable] = None,
        force: bool = False,
    ) -> PhoneAgent:
        """
        Initialize PhoneAgent for a device (thread-safe, idempotent).

        Args:
            device_id: Device identifier (USB serial / IP:port)
            model_config: Model configuration
            agent_config: Agent configuration
            takeover_callback: Optional takeover callback
            force: Force re-initialization even if agent exists

        Returns:
            PhoneAgent: Initialized agent instance

        Raises:
            AgentInitializationError: If initialization fails
            DeviceBusyError: If device is currently processing

        Transactional Guarantee:
            - On failure, state is rolled back
            - state.agents and state.agent_configs remain consistent
        """
        from phone_agent import PhoneAgent

        from AutoGLM_GUI.state import agent_configs, agents, non_blocking_takeover

        with self._manager_lock:
            # Check if already initialized
            if device_id in agents and not force:
                logger.debug(f"Agent already initialized for {device_id}")
                return agents[device_id]

            # Check device availability (non-blocking check)
            device_lock = self._get_device_lock(device_id)
            if device_lock.locked():
                raise DeviceBusyError(
                    f"Device {device_id} is currently processing a request"
                )

            # Set initializing state
            self._states[device_id] = AgentState.INITIALIZING

            try:
                # Create agent
                agent = PhoneAgent(
                    model_config=model_config,
                    agent_config=agent_config,
                    takeover_callback=takeover_callback or non_blocking_takeover,
                )

                # Store in state (transactional)
                agents[device_id] = agent
                agent_configs[device_id] = (model_config, agent_config)

                # Update metadata
                self._metadata[device_id] = AgentMetadata(
                    device_id=device_id,
                    state=AgentState.IDLE,
                    model_config=model_config,
                    agent_config=agent_config,
                    created_at=time.time(),
                    last_used=time.time(),
                )
                self._states[device_id] = AgentState.IDLE

                # Sync with DeviceManager
                from AutoGLM_GUI.device_manager import DeviceManager

                DeviceManager.get_instance().update_initialization_status(
                    device_id, True
                )

                logger.info(f"Agent initialized for device {device_id}")
                return agent

            except Exception as e:
                # Rollback on error
                agents.pop(device_id, None)
                agent_configs.pop(device_id, None)
                self._metadata.pop(device_id, None)
                self._states[device_id] = AgentState.ERROR

                logger.error(f"Failed to initialize agent for {device_id}: {e}")
                raise AgentInitializationError(
                    f"Failed to initialize agent: {str(e)}"
                ) from e

    def get_agent(self, device_id: str) -> PhoneAgent:
        """
        Get initialized agent for a device.

        Args:
            device_id: Device identifier

        Returns:
            PhoneAgent: Agent instance

        Raises:
            AgentNotInitializedError: If agent not initialized
        """
        from AutoGLM_GUI.state import agents

        with self._manager_lock:
            if device_id not in agents:
                raise AgentNotInitializedError(
                    f"Agent not initialized for device {device_id}. "
                    f"Call /api/init first."
                )
            return agents[device_id]

    def get_agent_safe(self, device_id: str) -> Optional[PhoneAgent]:
        """
        Get initialized agent for a device (safe version, no exception).

        Args:
            device_id: Device identifier

        Returns:
            PhoneAgent or None: Agent instance or None if not initialized
        """
        from AutoGLM_GUI.state import agents

        with self._manager_lock:
            return agents.get(device_id)

    def reset_agent(self, device_id: str) -> None:
        """
        Reset agent state and rebuild from cached config.

        Args:
            device_id: Device identifier

        Raises:
            AgentNotInitializedError: If agent not initialized
        """
        from phone_agent import PhoneAgent

        from AutoGLM_GUI.state import agent_configs, agents, non_blocking_takeover

        with self._manager_lock:
            if device_id not in agents:
                raise AgentNotInitializedError(
                    f"Agent not initialized for device {device_id}"
                )

            # Get cached config
            if device_id not in agent_configs:
                logger.warning(
                    f"No cached config for {device_id}, only resetting agent state"
                )
                agents[device_id].reset()
                return

            # Rebuild agent from cached config
            model_config, agent_config = agent_configs[device_id]

            agents[device_id] = PhoneAgent(
                model_config=model_config,
                agent_config=agent_config,
                takeover_callback=non_blocking_takeover,
            )

            # Update metadata
            if device_id in self._metadata:
                self._metadata[device_id].last_used = time.time()
                self._metadata[device_id].error_message = None

            self._states[device_id] = AgentState.IDLE

            logger.info(f"Agent reset for device {device_id}")

    def destroy_agent(self, device_id: str) -> None:
        """
        Destroy agent and clean up resources.

        Args:
            device_id: Device identifier
        """
        from AutoGLM_GUI.state import agent_configs, agents

        with self._manager_lock:
            # Remove agent
            agent = agents.pop(device_id, None)
            if agent:
                try:
                    agent.reset()  # Clean up agent state
                except Exception as e:
                    logger.warning(f"Error resetting agent during destroy: {e}")

            # Remove config
            agent_configs.pop(device_id, None)

            # Remove metadata
            self._metadata.pop(device_id, None)
            self._states.pop(device_id, None)

            # Sync with DeviceManager
            from AutoGLM_GUI.device_manager import DeviceManager

            DeviceManager.get_instance().update_initialization_status(device_id, False)

            logger.info(f"Agent destroyed for device {device_id}")

    def is_initialized(self, device_id: str) -> bool:
        """Check if agent is initialized for device."""
        from AutoGLM_GUI.state import agents

        with self._manager_lock:
            return device_id in agents

    # ==================== Concurrency Control ====================

    def _get_device_lock(self, device_id: str) -> threading.Lock:
        """
        Get or create device lock (double-checked locking pattern).

        Args:
            device_id: Device identifier

        Returns:
            threading.Lock: Device-specific lock
        """
        # Fast path: lock already exists
        if device_id in self._device_locks:
            return self._device_locks[device_id]

        # Slow path: create lock
        with self._device_locks_lock:
            # Double-check inside lock
            if device_id not in self._device_locks:
                self._device_locks[device_id] = threading.Lock()
            return self._device_locks[device_id]

    def acquire_device(
        self,
        device_id: str,
        timeout: Optional[float] = None,
        raise_on_timeout: bool = True,
    ) -> bool:
        """
        Acquire device lock for exclusive access.

        Args:
            device_id: Device identifier
            timeout: Lock acquisition timeout (None = blocking, 0 = non-blocking)
            raise_on_timeout: Raise DeviceBusyError on timeout

        Returns:
            bool: True if acquired, False if timeout (when raise_on_timeout=False)

        Raises:
            DeviceBusyError: If timeout and raise_on_timeout=True
            AgentNotInitializedError: If agent not initialized
        """
        # Verify agent exists
        if not self.is_initialized(device_id):
            raise AgentNotInitializedError(
                f"Agent not initialized for device {device_id}"
            )

        lock = self._get_device_lock(device_id)

        # Try to acquire with timeout
        if timeout is None:
            # Blocking mode
            acquired = lock.acquire(blocking=True)
        elif timeout == 0:
            # Non-blocking mode
            acquired = lock.acquire(blocking=False)
        else:
            # Timeout mode
            acquired = lock.acquire(blocking=True, timeout=timeout)

        if acquired:
            # Update state
            with self._manager_lock:
                self._states[device_id] = AgentState.BUSY
                if device_id in self._metadata:
                    self._metadata[device_id].last_used = time.time()

            logger.debug(f"Device lock acquired for {device_id}")
            return True
        else:
            if raise_on_timeout:
                raise DeviceBusyError(
                    f"Device {device_id} is busy, could not acquire lock"
                    + (f" within {timeout}s" if timeout else "")
                )
            return False

    def release_device(self, device_id: str) -> None:
        """
        Release device lock.

        Args:
            device_id: Device identifier
        """
        lock = self._get_device_lock(device_id)

        if lock.locked():
            lock.release()

            # Update state
            with self._manager_lock:
                self._states[device_id] = AgentState.IDLE

            logger.debug(f"Device lock released for {device_id}")

    @contextmanager
    def use_agent(self, device_id: str, timeout: Optional[float] = None):
        """
        Context manager for automatic lock acquisition/release.

        Args:
            device_id: Device identifier
            timeout: Lock acquisition timeout

        Yields:
            PhoneAgent: Agent instance

        Raises:
            DeviceBusyError: If device is busy
            AgentNotInitializedError: If agent not initialized

        Example:
            >>> manager = PhoneAgentManager.get_instance()
            >>> with manager.use_agent("device_123") as agent:
            >>>     result = agent.run("Open WeChat")
        """
        acquired = False
        try:
            acquired = self.acquire_device(device_id, timeout, raise_on_timeout=True)
            agent = self.get_agent(device_id)
            yield agent
        except Exception as exc:
            # Handle errors
            self.set_error_state(device_id, str(exc))
            raise
        finally:
            if acquired:
                self.release_device(device_id)

    # ==================== State Management ====================

    def get_state(self, device_id: str) -> AgentState:
        """Get current agent state."""
        with self._manager_lock:
            return self._states.get(device_id, AgentState.ERROR)

    def set_error_state(self, device_id: str, error_message: str) -> None:
        """Mark agent as errored."""
        with self._manager_lock:
            self._states[device_id] = AgentState.ERROR
            if device_id in self._metadata:
                self._metadata[device_id].error_message = error_message

            logger.error(f"Agent error for {device_id}: {error_message}")

    # ==================== Configuration Management ====================

    def get_config(self, device_id: str) -> tuple[ModelConfig, AgentConfig]:
        """Get cached configuration for device."""
        from AutoGLM_GUI.state import agent_configs

        with self._manager_lock:
            if device_id not in agent_configs:
                raise AgentNotInitializedError(
                    f"No configuration found for device {device_id}"
                )
            return agent_configs[device_id]

    def update_config(
        self,
        device_id: str,
        model_config: Optional[ModelConfig] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> None:
        """
        Update agent configuration (requires reinitialization).

        Args:
            device_id: Device identifier
            model_config: New model config (None = keep existing)
            agent_config: New agent config (None = keep existing)
        """
        from AutoGLM_GUI.state import agent_configs

        with self._manager_lock:
            if device_id not in agent_configs:
                raise AgentNotInitializedError(
                    f"No configuration found for device {device_id}"
                )

            old_model_config, old_agent_config = agent_configs[device_id]

            new_model_config = model_config or old_model_config
            new_agent_config = agent_config or old_agent_config

            # Reinitialize with new config
            self.initialize_agent(
                device_id,
                new_model_config,
                new_agent_config,
                force=True,
            )

    # ==================== DeviceManager Integration ====================

    def find_agent_by_serial(self, serial: str) -> Optional[str]:
        """
        Find agent device_id by hardware serial (connection switching support).

        Delegates to DeviceManager.get_agent_by_serial().

        Args:
            serial: Hardware serial number

        Returns:
            Optional[str]: device_id of initialized agent, or None
        """
        from AutoGLM_GUI.device_manager import DeviceManager

        return DeviceManager.get_instance().get_agent_by_serial(serial)

    # ==================== Introspection ====================

    def list_agents(self) -> list[str]:
        """Get list of all initialized device IDs."""
        from AutoGLM_GUI.state import agents

        with self._manager_lock:
            return list(agents.keys())

    def get_metadata(self, device_id: str) -> Optional[AgentMetadata]:
        """Get agent metadata."""
        with self._manager_lock:
            return self._metadata.get(device_id)
