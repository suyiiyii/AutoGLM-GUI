"""Agent lifecycle and concurrency manager (singleton)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from AutoGLM_GUI.agents.protocols import BaseAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.exceptions import (
    AgentInitializationError,
    AgentNotInitializedError,
    DeviceBusyError,
)
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.types import AgentSpecificConfig


class AgentState(str, Enum):
    """Agent runtime state."""

    IDLE = "idle"  # Agent initialized, not processing
    BUSY = "busy"  # Agent processing a request
    ERROR = "error"  # Agent encountered error
    INITIALIZING = "initializing"  # Agent being created


@dataclass
class AgentMetadata:
    """Metadata for an agent instance."""

    device_id: str
    state: AgentState
    model_config: ModelConfig
    agent_config: AgentConfig
    agent_type: str = "glm"
    created_at: float = 0.0
    last_used: float = 0.0
    error_message: Optional[str] = None


@dataclass
class StreamingAgentContext:
    streaming_agent: BaseAgent
    original_agent: BaseAgent
    stop_event: threading.Event


class PhoneAgentManager:
    """
    Singleton manager for agent lifecycle and concurrency control.

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
        >>> # Use agent with automatic locking (auto-initializes if needed)
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
        # State is stored in AgentMetadata.state (single source of truth)
        self._metadata: dict[str, AgentMetadata] = {}

        # Streaming agent state (device_id -> StreamingAgentContext)
        self._streaming_contexts: dict[str, StreamingAgentContext] = {}
        self._streaming_contexts_lock = threading.Lock()

        self._abort_events: dict[str, threading.Event | Callable[[], None]] = {}

        # Agent storage (transition from global state to instance state)
        self._agents: dict[str, BaseAgent] = {}
        self._agent_configs: dict[str, tuple[ModelConfig, AgentConfig]] = {}

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

    def initialize_agent_with_factory(
        self,
        device_id: str,
        agent_type: str,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        agent_specific_config: AgentSpecificConfig,
        takeover_callback: Optional[Callable] = None,
        confirmation_callback: Optional[Callable] = None,
        force: bool = False,
    ) -> "BaseAgent":
        from AutoGLM_GUI.agents import create_agent

        with self._manager_lock:
            if device_id in self._agents and not force:
                logger.debug(f"Agent already initialized for {device_id}")
                return self._agents[device_id]

            device_lock = self._get_device_lock(device_id)
            if device_lock.locked():
                raise DeviceBusyError(
                    f"Device {device_id} is currently processing a request"
                )

            self._metadata[device_id] = AgentMetadata(
                device_id=device_id,
                state=AgentState.INITIALIZING,
                model_config=model_config,
                agent_config=agent_config,
                agent_type=agent_type,
                created_at=time.time(),
                last_used=time.time(),
            )

            try:
                from AutoGLM_GUI.device_manager import DeviceManager

                device_manager = DeviceManager.get_instance()
                try:
                    device = device_manager.get_device_protocol(device_id)
                except ValueError:
                    # Ensure cold starts refresh device cache before failing.
                    device_manager.force_refresh()
                    device = device_manager.get_device_protocol(device_id)

                agent = create_agent(
                    agent_type=agent_type,
                    model_config=model_config,
                    agent_config=agent_config,
                    agent_specific_config=agent_specific_config,
                    device=device,
                    takeover_callback=takeover_callback,
                    confirmation_callback=confirmation_callback,
                )

                self._agents[device_id] = agent
                self._agent_configs[device_id] = (model_config, agent_config)

                self._metadata[device_id].state = AgentState.IDLE

                logger.info(
                    f"Agent of type '{agent_type}' initialized for device {device_id}"
                )
                return agent

            except Exception as e:
                self._agents.pop(device_id, None)
                self._agent_configs.pop(device_id, None)
                self._metadata[device_id].state = AgentState.ERROR
                self._metadata[device_id].error_message = str(e)

                logger.error(f"Failed to initialize agent for {device_id}: {e}")
                raise AgentInitializationError(
                    f"Failed to initialize agent: {str(e)}"
                ) from e

    def _auto_initialize_agent(self, device_id: str) -> None:
        """
        使用全局配置自动初始化 agent（内部方法，需在 manager_lock 内调用）.

        使用 factory 模式创建 agent，避免直接依赖 phone_agent.PhoneAgent。

        Args:
            device_id: 设备标识符

        Raises:
            AgentInitializationError: 如果配置不完整或初始化失败
        """
        from typing import cast

        from AutoGLM_GUI.config import AgentConfig, ModelConfig
        from AutoGLM_GUI.config_manager import config_manager
        from AutoGLM_GUI.types import AgentSpecificConfig

        logger.info(f"Auto-initializing agent for device {device_id}...")

        # 热重载配置
        config_manager.load_file_config()
        config_manager.sync_to_env()

        effective_config = config_manager.get_effective_config()

        if not effective_config.base_url:
            raise AgentInitializationError(
                f"Cannot auto-initialize agent for {device_id}: base_url not configured. "
                f"Please configure base_url via /api/config or call /api/init explicitly."
            )

        # 使用本地配置类型
        model_config = ModelConfig(
            base_url=effective_config.base_url,
            api_key=effective_config.api_key,
            model_name=effective_config.model_name,
        )

        agent_config = AgentConfig(device_id=device_id)

        # 调用 factory 方法创建 agent（避免直接依赖 phone_agent）
        agent_specific_config = cast(
            AgentSpecificConfig, effective_config.agent_config_params or {}
        )
        self.initialize_agent_with_factory(
            device_id=device_id,
            agent_type=effective_config.agent_type,
            model_config=model_config,
            agent_config=agent_config,
            agent_specific_config=agent_specific_config,
        )
        logger.info(f"Agent auto-initialized for device {device_id}")

    def get_agent(self, device_id: str) -> BaseAgent:
        with self._manager_lock:
            if device_id not in self._agents:
                self._auto_initialize_agent(device_id)
            return self._agents[device_id]

    def get_agent_safe(self, device_id: str) -> Optional[BaseAgent]:
        with self._manager_lock:
            return self._agents.get(device_id)

    def reset_agent(self, device_id: str) -> None:
        """
        Reset agent state by calling the agent's reset() method.

        Args:
            device_id: Device identifier

        Raises:
            AgentNotInitializedError: If agent not initialized
        """
        with self._manager_lock:
            if device_id not in self._agents:
                raise AgentNotInitializedError(
                    f"Agent not initialized for device {device_id}"
                )

            # Reset agent state using its reset() method
            self._agents[device_id].reset()

            # Update metadata
            if device_id in self._metadata:
                self._metadata[device_id].last_used = time.time()
                self._metadata[device_id].error_message = None
                self._metadata[device_id].state = AgentState.IDLE

            logger.info(f"Agent reset for device {device_id}")

    def destroy_agent(self, device_id: str) -> None:
        """
        Destroy agent and clean up resources.

        Args:
            device_id: Device identifier
        """
        with self._manager_lock:
            # Remove agent
            agent = self._agents.pop(device_id, None)
            if agent:
                try:
                    agent.reset()  # Clean up agent state
                except Exception as e:
                    logger.warning(f"Error resetting agent during destroy: {e}")

            # Remove config
            self._agent_configs.pop(device_id, None)

            # Remove metadata
            self._metadata.pop(device_id, None)

            logger.info(f"Agent destroyed for device {device_id}")

    def is_initialized(self, device_id: str) -> bool:
        """Check if agent is initialized for device."""
        with self._manager_lock:
            return device_id in self._agents

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
        auto_initialize: bool = False,
    ) -> bool:
        """
        Acquire device lock for exclusive access.

        Args:
            device_id: Device identifier
            timeout: Lock acquisition timeout (None = blocking, 0 = non-blocking)
            raise_on_timeout: Raise DeviceBusyError on timeout
            auto_initialize: Auto-initialize agent if not already initialized (default: False)

        Returns:
            bool: True if acquired, False if timeout (when raise_on_timeout=False)

        Raises:
            DeviceBusyError: If timeout and raise_on_timeout=True
            AgentNotInitializedError: If agent not initialized AND auto_initialize=False
            AgentInitializationError: If auto_initialize=True and initialization fails
        """
        # Verify agent exists (with optional auto-initialization)
        if not self.is_initialized(device_id):
            if auto_initialize:
                # Double-check locking pattern for thread safety
                with self._manager_lock:
                    if not self.is_initialized(device_id):
                        self._auto_initialize_agent(device_id)
            else:
                raise AgentNotInitializedError(
                    f"Agent not initialized for device {device_id}. "
                    f"Use auto_initialize=True or call initialize_agent() first."
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
                if device_id in self._metadata:
                    self._metadata[device_id].state = AgentState.BUSY
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
                if device_id in self._metadata:
                    self._metadata[device_id].state = AgentState.IDLE

            logger.debug(f"Device lock released for {device_id}")

    @contextmanager
    def use_agent(
        self,
        device_id: str,
        timeout: Optional[float] = None,
        auto_initialize: bool = True,
    ):
        """
        Context manager for automatic lock acquisition/release.

        By default, automatically initializes the agent using global configuration
        if not already initialized. Set auto_initialize=False to require explicit
        initialization via initialize_agent_with_factory().

        Args:
            device_id: Device identifier
            timeout: Lock acquisition timeout
            auto_initialize: Auto-initialize if not already initialized (default: True)

        Yields:
            BaseAgent: Agent instance

        Raises:
            DeviceBusyError: If device is busy
            AgentNotInitializedError: If agent not initialized AND auto_initialize=False
            AgentInitializationError: If auto_initialize=True and initialization fails

        Example:
            >>> manager = PhoneAgentManager.get_instance()
            >>> with manager.use_agent("device_123") as agent:  # Auto-initializes
            >>>     result = agent.run("Open WeChat")
            >>> with manager.use_agent("device_123", auto_initialize=False) as agent:
            >>>     result = agent.run("Open WeChat")  # Requires prior init
        """
        acquired = False
        try:
            acquired = self.acquire_device(
                device_id,
                timeout,
                raise_on_timeout=True,
                auto_initialize=auto_initialize,
            )
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
            metadata = self._metadata.get(device_id)
            return metadata.state if metadata else AgentState.ERROR

    def set_error_state(self, device_id: str, error_message: str) -> None:
        """Mark agent as errored."""
        with self._manager_lock:
            if device_id in self._metadata:
                self._metadata[device_id].state = AgentState.ERROR
                self._metadata[device_id].error_message = error_message

            logger.error(f"Agent error for {device_id}: {error_message}")

    # ==================== Configuration Management ====================

    def get_config(self, device_id: str) -> tuple[ModelConfig, AgentConfig]:
        """Get cached configuration for device."""
        with self._manager_lock:
            if device_id not in self._agent_configs:
                raise AgentNotInitializedError(
                    f"No configuration found for device {device_id}"
                )
            return self._agent_configs[device_id]

    # ==================== Introspection ====================

    def list_agents(self) -> list[str]:
        """Get list of all initialized device IDs."""
        with self._manager_lock:
            return list(self._agents.keys())

    def get_metadata(self, device_id: str) -> Optional[AgentMetadata]:
        """Get agent metadata."""
        with self._manager_lock:
            return self._metadata.get(device_id)

    def register_abort_handler(
        self, device_id: str, abort_handler: threading.Event | Callable[[], None]
    ) -> None:
        with self._streaming_contexts_lock:
            self._abort_events[device_id] = abort_handler

    def unregister_abort_handler(self, device_id: str) -> None:
        with self._streaming_contexts_lock:
            self._abort_events.pop(device_id, None)

    def abort_streaming_chat(self, device_id: str) -> bool:
        """
        中止正在进行的流式对话.

        Args:
            device_id: 设备标识符

        Returns:
            bool: True 表示发送了中止信号，False 表示没有活跃会话
        """
        with self._streaming_contexts_lock:
            if device_id in self._abort_events:
                logger.info(f"Aborting streaming chat for device {device_id}")
                handler = self._abort_events[device_id]
                if isinstance(handler, threading.Event):
                    handler.set()
                elif callable(handler):
                    handler()
                return True
            else:
                logger.warning(f"No active streaming chat for device {device_id}")
                return False

    def is_streaming_active(self, device_id: str) -> bool:
        """检查设备是否有活跃的流式会话."""
        with self._streaming_contexts_lock:
            return device_id in self._abort_events
