"""PhoneAgent lifecycle and concurrency manager (singleton)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

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

    # Base agent interface (protocol)
    class BaseAgent:
        """Common interface that all agents must implement."""

        def run(self, task: str) -> str: ...
        def step(self, task: str | None) -> Any: ...  # StepResult
        def reset(self) -> None: ...
        @property
        def step_count(self) -> int: ...


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


@dataclass
class StreamingAgentContext:
    """Streaming agent 会话上下文."""

    streaming_agent: "PhoneAgent"
    original_agent: "PhoneAgent"
    stop_event: threading.Event


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

        # Streaming agent state (device_id -> StreamingAgentContext)
        self._streaming_contexts: dict[str, StreamingAgentContext] = {}
        self._streaming_contexts_lock = threading.Lock()

        # Abort events (device_id -> threading.Event)
        self._abort_events: dict[str, threading.Event] = {}

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

    def initialize_agent_with_factory(
        self,
        device_id: str,
        agent_type: str,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        agent_specific_config: dict[str, Any],
        takeover_callback: Optional[Callable] = None,
        confirmation_callback: Optional[Callable] = None,
        force: bool = False,
    ) -> "BaseAgent":
        """
        Initialize agent using factory pattern (thread-safe, idempotent).

        This method uses the agent factory to create agents dynamically based on agent_type.
        New agent types can be added without modifying this method by registering them.

        Args:
            device_id: Device identifier (USB serial / IP:port)
            agent_type: Type of agent to create (e.g., "phone", "mai")
            model_config: Model configuration
            agent_config: Agent configuration
            agent_specific_config: Agent-specific configuration dict
            takeover_callback: Optional takeover callback
            confirmation_callback: Optional confirmation callback
            force: Force re-initialization even if agent exists

        Returns:
            BaseAgent: Initialized agent instance

        Raises:
            AgentInitializationError: If initialization fails
            DeviceBusyError: If device is currently processing

        Transactional Guarantee:
            - On failure, state is rolled back
            - state.agents and state.agent_configs remain consistent
        """
        from AutoGLM_GUI.agents import create_agent

        from AutoGLM_GUI.state import agent_configs, agents

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
                # Create agent using factory
                agent = create_agent(
                    agent_type=agent_type,
                    model_config=model_config,
                    agent_config=agent_config,
                    agent_specific_config=agent_specific_config,
                    takeover_callback=takeover_callback,
                    confirmation_callback=confirmation_callback,
                )

                # Store in state (transactional)
                agents[device_id] = agent
                agent_configs[device_id] = (model_config, agent_config)

                # Update metadata (store agent_type for reference)
                self._metadata[device_id] = AgentMetadata(
                    device_id=device_id,
                    state=AgentState.IDLE,
                    model_config=model_config,
                    agent_config=agent_config,
                    created_at=time.time(),
                    last_used=time.time(),
                )
                self._states[device_id] = AgentState.IDLE

                logger.info(
                    f"Agent of type '{agent_type}' initialized for device {device_id}"
                )
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

    def _create_streaming_agent(
        self,
        device_id: str,
        original_agent: "BaseAgent",
        on_thinking_chunk: Callable[[str], None],
    ) -> "BaseAgent":
        """
        创建支持流式输出的 agent（复制原始 agent）.

        Args:
            device_id: 设备标识符
            original_agent: 原始 agent 实例
            on_thinking_chunk: 思考块回调函数

        Returns:
            已 patch 的 agent 实例
        """
        from AutoGLM_GUI.agents.mai_adapter import MAIAgentAdapter
        from phone_agent import PhoneAgent

        model_config, agent_config = self.get_config(device_id)

        if isinstance(original_agent, MAIAgentAdapter):
            # 创建 MAI Agent streaming 实例
            streaming_agent = MAIAgentAdapter(
                model_config=model_config,
                agent_config=agent_config,
                mai_config=original_agent.mai_config,
                takeover_callback=original_agent.action_handler.takeover_callback,
                confirmation_callback=original_agent.action_handler.confirmation_callback,
                on_thinking_chunk=on_thinking_chunk,
            )
            # 复制轨迹状态
            streaming_agent.mai_agent.traj_memory = original_agent.mai_agent.traj_memory
            streaming_agent._step_count = original_agent._step_count
            streaming_agent._current_instruction = original_agent._current_instruction
        else:
            # 创建 PhoneAgent streaming 实例
            from AutoGLM_GUI.state import non_blocking_takeover

            streaming_agent = PhoneAgent(
                model_config=model_config,
                agent_config=agent_config,
                takeover_callback=non_blocking_takeover,
            )

            # Monkey-patch model_client.request 以支持流式回调
            original_request = streaming_agent.model_client.request

            def patched_request(messages, **kwargs):
                return original_request(messages, on_thinking_chunk=on_thinking_chunk)

            streaming_agent.model_client.request = patched_request

            # 复制上下文
            streaming_agent._context = original_agent._context.copy()
            streaming_agent._step_count = original_agent._step_count

        return streaming_agent

    @contextmanager
    def use_streaming_agent(
        self,
        device_id: str,
        on_thinking_chunk: Callable[[str], None],
        timeout: Optional[float] = None,
        auto_initialize: bool = True,
    ):
        """
        Context manager for streaming-enabled agent with automatic:
        - 设备锁获取/释放
        - Streaming agent 创建（带 monkey-patch）
        - 上下文隔离和同步
        - Abort 事件注册/清理

        By default, automatically initializes the agent using global configuration
        if not already initialized. Set auto_initialize=False to require explicit
        initialization via initialize_agent().

        Args:
            device_id: 设备标识符
            on_thinking_chunk: 流式思考块回调函数
            timeout: 锁获取超时时间（None=阻塞，0=非阻塞）
            auto_initialize: 自动初始化（默认: True）

        Yields:
            tuple[PhoneAgent, threading.Event]: (streaming_agent, stop_event)

        Raises:
            DeviceBusyError: 设备忙
            AgentNotInitializedError: Agent 未初始化且 auto_initialize=False
            AgentInitializationError: auto_initialize=True 且初始化失败

        Example:
            >>> def on_chunk(chunk: str):
            >>>     print(chunk, end='', flush=True)
            >>>
            >>> with manager.use_streaming_agent("device_123", on_chunk) as (agent, stop_event):
            >>>     result = agent.step("Open WeChat")
        """
        acquired = False
        streaming_agent = None
        stop_event = threading.Event()

        try:
            # 获取设备锁（默认非阻塞）
            acquired = self.acquire_device(
                device_id,
                timeout=timeout if timeout is not None else 0,
                raise_on_timeout=True,
                auto_initialize=auto_initialize,
            )

            # 获取原始 agent
            original_agent = self.get_agent(device_id)

            # 创建 streaming agent（自动检测类型）
            streaming_agent = self._create_streaming_agent(
                device_id=device_id,
                original_agent=original_agent,
                on_thinking_chunk=on_thinking_chunk,
            )

            # 注册 abort 事件
            with self._streaming_contexts_lock:
                self._abort_events[device_id] = stop_event
                self._streaming_contexts[device_id] = StreamingAgentContext(
                    streaming_agent=streaming_agent,
                    original_agent=original_agent,
                    stop_event=stop_event,
                )

            logger.debug(f"Streaming agent created for {device_id}")

            yield streaming_agent, stop_event

        finally:
            # 同步状态回原始 agent
            if streaming_agent and not stop_event.is_set():
                original_agent = self.get_agent_safe(device_id)
                if original_agent:
                    from AutoGLM_GUI.agents.mai_adapter import MAIAgentAdapter

                    if isinstance(original_agent, MAIAgentAdapter):
                        # 同步 MAI Agent 状态
                        original_agent.mai_agent.traj_memory = (
                            streaming_agent.mai_agent.traj_memory
                        )
                        original_agent._step_count = streaming_agent._step_count
                        original_agent._current_instruction = (
                            streaming_agent._current_instruction
                        )
                    else:
                        # 同步 PhoneAgent 状态
                        original_agent._context = streaming_agent._context
                        original_agent._step_count = streaming_agent._step_count

                    logger.debug(
                        f"Synchronized context back to original agent for {device_id}"
                    )

            # 清理 abort 事件注册
            with self._streaming_contexts_lock:
                self._abort_events.pop(device_id, None)
                self._streaming_contexts.pop(device_id, None)

            # 释放设备锁
            if acquired:
                self.release_device(device_id)

    def _auto_initialize_agent(self, device_id: str) -> None:
        """
        使用全局配置自动初始化 agent（内部方法，需在 manager_lock 内调用）.

        Args:
            device_id: 设备标识符

        Raises:
            AgentInitializationError: 如果配置不完整或初始化失败
        """
        from phone_agent.agent import AgentConfig
        from phone_agent.model import ModelConfig

        from AutoGLM_GUI.config import config
        from AutoGLM_GUI.config_manager import config_manager

        logger.info(f"Auto-initializing agent for device {device_id}...")

        # 热重载配置
        config_manager.load_file_config()
        config_manager.sync_to_env()
        config.refresh_from_env()

        effective_config = config_manager.get_effective_config()

        if not effective_config.base_url:
            raise AgentInitializationError(
                f"Cannot auto-initialize agent for {device_id}: base_url not configured. "
                f"Please configure base_url via /api/config or call /api/init explicitly."
            )

        model_config = ModelConfig(
            base_url=effective_config.base_url,
            api_key=effective_config.api_key,
            model_name=effective_config.model_name,
        )

        agent_config = AgentConfig(device_id=device_id)

        # 调用 initialize_agent（RLock 支持重入，不会死锁）
        self.initialize_agent(device_id, model_config, agent_config)
        logger.info(f"Agent auto-initialized for device {device_id}")

    def get_agent(self, device_id: str) -> PhoneAgent:
        """
        Get initialized agent for a device.

        Auto-initializes the agent using global config if not already initialized.

        Args:
            device_id: Device identifier

        Returns:
            PhoneAgent: Agent instance

        Raises:
            AgentInitializationError: If agent not initialized and auto-init fails
        """
        from AutoGLM_GUI.state import agents

        with self._manager_lock:
            if device_id not in agents:
                # 自动初始化：使用全局配置
                self._auto_initialize_agent(device_id)
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
        initialization via initialize_agent().

        Args:
            device_id: Device identifier
            timeout: Lock acquisition timeout
            auto_initialize: Auto-initialize if not already initialized (default: True)

        Yields:
            PhoneAgent: Agent instance

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

        Args:
            serial: Hardware serial number

        Returns:
            Optional[str]: device_id of initialized agent, or None
        """
        from AutoGLM_GUI.device_manager import DeviceManager
        from AutoGLM_GUI.state import agents

        with self._manager_lock:
            # Get device by serial from DeviceManager
            device_manager = DeviceManager.get_instance()
            device = device_manager._devices.get(serial)

            if not device:
                return None

            # Check all connections for initialized agents
            for conn in device.connections:
                if conn.device_id in agents:
                    return conn.device_id

            return None

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
                self._abort_events[device_id].set()
                return True
            else:
                logger.warning(f"No active streaming chat for device {device_id}")
                return False

    def is_streaming_active(self, device_id: str) -> bool:
        """检查设备是否有活跃的流式会话."""
        with self._streaming_contexts_lock:
            return device_id in self._abort_events
