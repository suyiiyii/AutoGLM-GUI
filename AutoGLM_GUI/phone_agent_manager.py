"""Agent lifecycle and concurrency manager (singleton)."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum

from AutoGLM_GUI.agents.protocols import AsyncAgent, BaseAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.exceptions import (
    AgentInitializationError,
    AgentNotInitializedError,
    DeviceBusyError,
)
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.types import AgentSpecificConfig


class AgentState(StrEnum):
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
    agent_type: str = "glm-async"
    created_at: float = 0.0
    last_used: float = 0.0
    error_message: str | None = None
    abort_handler: (
        threading.Event | Callable[[], None] | Callable[[], Awaitable[None]] | None
    ) = None


class PhoneAgentManager:
    """
    Singleton manager for agent lifecycle and concurrency control.

    Features:
    - Thread-safe agent creation/destruction
    - Atomic state-machine concurrency (IDLE↔BUSY transitions)
    - State management (IDLE/BUSY/ERROR/INITIALIZING)
    - Integration with DeviceManager
    - Configuration hot-reload support
    - Connection switching detection

    Design Principles:
    - Uses state.agents and state.agent_configs as storage (backward compatible)
    - Single RLock (_manager_lock) for all state transitions (microsecond hold time)
    - No long-held per-device locks; acquire/release are instantaneous CAS operations
    - Context managers for automatic state release

    Example:
        >>> manager = PhoneAgentManager.get_instance()
        >>>
        >>> # Use agent with automatic locking (auto-initializes if needed)
        >>> with manager.use_agent(device_id) as agent:
        >>>     result = agent.run("Open WeChat")
    """

    _instance: PhoneAgentManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self):
        """Private constructor. Use get_instance() instead."""
        # Manager-level lock (protects internal state)
        # All state transitions (IDLE↔BUSY) are guarded by this single lock.
        # Each critical section holds it for microseconds only (atomic CAS),
        # so no asyncio.to_thread() wrapper is needed for release/register/unregister.
        self._manager_lock = threading.RLock()

        # Agent metadata (indexed by device_id)
        # State is stored in AgentMetadata.state (single source of truth)
        self._metadata: dict[str, AgentMetadata] = {}

        # Agent storage (transition from global state to instance state)
        # Agents can be either AsyncAgent or BaseAgent depending on agent_type
        self._agents: dict[str, AsyncAgent | BaseAgent] = {}
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
        takeover_callback: Callable | None = None,
        confirmation_callback: Callable | None = None,
        force: bool = False,
    ) -> AsyncAgent | BaseAgent:
        from AutoGLM_GUI.agents import create_agent

        with self._manager_lock:
            if device_id in self._agents and not force:
                logger.debug(f"Agent already initialized for {device_id}")
                return self._agents[device_id]

            metadata = self._metadata.get(device_id)
            if metadata and metadata.state == AgentState.BUSY:
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
                # Use agent_config.device_id (actual device ID) instead of device_id (storage key)
                # to get device protocol, as device_id may be a composite key like "device_id:context"
                actual_device_id = agent_config.device_id
                if not actual_device_id:
                    raise AgentInitializationError(
                        "agent_config.device_id is required but was None"
                    )
                try:
                    device = device_manager.get_device_protocol(actual_device_id)
                except ValueError:
                    # Ensure cold starts refresh device cache before failing.
                    device_manager.force_refresh()
                    device = device_manager.get_device_protocol(actual_device_id)

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

    def _auto_initialize_agent(
        self, agent_key: str, actual_device_id: str, agent_type: str | None = None
    ) -> None:
        """
        使用全局配置自动初始化 agent（内部方法，需在 manager_lock 内调用）.

        使用 factory 模式创建 agent，避免直接依赖 phone_agent.PhoneAgent。

        Args:
            agent_key: Agent 存储键（可能是 device_id 或 device_id:context）
            actual_device_id: 实际设备标识符（用于设备操作）
            agent_type: 可选的 agent 类型覆盖

        Raises:
            AgentInitializationError: 如果配置不完整或初始化失败
        """
        from typing import cast

        from AutoGLM_GUI.config import AgentConfig, ModelConfig
        from AutoGLM_GUI.config_manager import config_manager
        from AutoGLM_GUI.types import AgentSpecificConfig

        logger.info(
            f"Auto-initializing agent for key {agent_key} (device: {actual_device_id})..."
        )

        # 热重载配置
        config_manager.load_file_config()
        config_manager.sync_to_env()

        effective_config = config_manager.get_effective_config()

        if not effective_config.base_url:
            raise AgentInitializationError(
                f"Cannot auto-initialize agent for {agent_key}: base_url not configured. "
                f"Please configure base_url via /api/config before sending tasks."
            )

        # 使用本地配置类型
        model_config = ModelConfig(
            base_url=effective_config.base_url,
            api_key=effective_config.api_key,
            model_name=effective_config.model_name,
        )

        # 使用实际的 device_id 创建 AgentConfig
        agent_config = AgentConfig(device_id=actual_device_id)

        # 调用 factory 方法创建 agent（避免直接依赖 phone_agent）
        agent_specific_config = cast(
            AgentSpecificConfig, effective_config.agent_config_params or {}
        )
        # 使用提供的 agent_type 或从配置中获取
        effective_agent_type = agent_type or effective_config.agent_type
        self.initialize_agent_with_factory(
            device_id=agent_key,
            agent_type=effective_agent_type,
            model_config=model_config,
            agent_config=agent_config,
            agent_specific_config=agent_specific_config,
        )
        logger.info(f"Agent auto-initialized for key {agent_key}")

    def get_agent(self, device_id: str) -> AsyncAgent | BaseAgent:
        """Get agent using default context (backward compatible)."""
        return self.get_agent_with_context(device_id, context="default")

    def get_agent_with_context(
        self,
        device_id: str,
        context: str = "default",
        agent_type: str | None = None,
    ) -> AsyncAgent | BaseAgent:
        """Get or create agent for specific context.

        Args:
            device_id: Device identifier
            context: Context identifier (e.g., "chat", "default")
            agent_type: Optional agent type override

        Returns:
            Agent instance for this device+context combination
        """
        with self._manager_lock:
            agent_key = self._make_agent_key(device_id, context)

            if agent_key not in self._agents:
                self._auto_initialize_agent(agent_key, device_id, agent_type=agent_type)

            return self._agents[agent_key]

    def get_agent_safe(self, device_id: str) -> AsyncAgent | BaseAgent | None:
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

    def _make_agent_key(self, device_id: str, context: str = "default") -> str:
        """Build composite key for device+context isolation."""
        return device_id if context == "default" else f"{device_id}:{context}"

    def acquire_device(
        self,
        device_id: str,
        auto_initialize: bool = False,
        timeout: float | None = None,
        raise_on_timeout: bool = True,
        context: str = "default",
    ) -> bool:
        """
        Atomically transition device state from IDLE to BUSY.

        This is an instantaneous CAS (compare-and-swap) operation protected by
        ``_manager_lock`` (held for microseconds). It is safe to call from both
        sync and async contexts without ``asyncio.to_thread``, **except** when
        ``auto_initialize=True`` — auto-initialization may perform I/O, so
        callers should still wrap that case in ``asyncio.to_thread``.

        Args:
            device_id: Device identifier
            auto_initialize: Auto-initialize agent if not already initialized
            timeout: Ignored (kept for backward compatibility). The operation
                is non-blocking and completes instantly.
            raise_on_timeout: If True (default), raise DeviceBusyError when
                device is BUSY. If False, return False instead.
            context: Context identifier for key isolation (e.g., "mcp", "layered").
                Defaults to "default" for backward compatibility.

        Returns:
            bool: True if state was IDLE and is now BUSY, False if device is
                BUSY and raise_on_timeout=False

        Raises:
            DeviceBusyError: If device is already BUSY and raise_on_timeout=True
            AgentNotInitializedError: If agent not initialized AND auto_initialize=False
            AgentInitializationError: If auto_initialize=True and initialization fails
        """
        agent_key = self._make_agent_key(device_id, context)

        # Verify agent exists (with optional auto-initialization)
        if not self.is_initialized(agent_key):
            if auto_initialize:
                with self._manager_lock:
                    if not self.is_initialized(agent_key):
                        self._auto_initialize_agent(agent_key, device_id)
            else:
                raise AgentNotInitializedError(
                    f"Agent not initialized for device {agent_key}. "
                    f"Use auto_initialize=True or call initialize_agent() first."
                )

        # Atomic CAS: IDLE → BUSY
        with self._manager_lock:
            metadata = self._metadata.get(agent_key)
            if metadata and metadata.state == AgentState.BUSY:
                if raise_on_timeout:
                    raise DeviceBusyError(
                        f"Device {agent_key} is busy, could not acquire lock"
                    )
                return False
            if metadata:
                metadata.state = AgentState.BUSY
                metadata.last_used = time.time()

        logger.debug(f"Device lock acquired for {agent_key}")
        return True

    async def acquire_device_async(
        self,
        device_id: str,
        auto_initialize: bool = False,
        timeout: float | None = None,
        raise_on_timeout: bool = True,
        context: str = "default",
    ) -> bool:
        """Acquire a device lock without leaking it if the awaiter is cancelled."""

        acquire_task = asyncio.create_task(
            asyncio.to_thread(
                self.acquire_device,
                device_id,
                auto_initialize=auto_initialize,
                timeout=timeout,
                raise_on_timeout=raise_on_timeout,
                context=context,
            )
        )

        try:
            return await asyncio.shield(acquire_task)
        except asyncio.CancelledError:

            def _cleanup_cancelled_acquire(task: asyncio.Task[bool]) -> None:
                try:
                    acquired = task.result()
                except Exception:
                    return

                if not acquired:
                    return

                try:
                    self.release_device(device_id, context=context)
                except BaseException as e:
                    logger.error(
                        f"Failed to cleanup cancelled acquire for {device_id}: {e}"
                    )

            acquire_task.add_done_callback(_cleanup_cancelled_acquire)
            raise

    def release_device(self, device_id: str, context: str = "default") -> None:
        """
        Atomically transition device state from BUSY to IDLE and clear abort handler.

        This is an instantaneous operation (microsecond lock hold). Safe to call
        directly from async ``finally`` blocks — no ``asyncio.to_thread`` needed,
        so it cannot be interrupted by ``CancelledError``.

        Args:
            device_id: Device identifier
            context: Context identifier, must match the one used in acquire_device.
        """
        agent_key = self._make_agent_key(device_id, context)
        with self._manager_lock:
            metadata = self._metadata.get(agent_key)
            if metadata:
                metadata.state = AgentState.IDLE
                metadata.abort_handler = None

        logger.debug(f"Device lock released for {agent_key}")

    @contextmanager
    def use_agent(
        self,
        device_id: str,
        timeout: float | None = None,
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

    def get_metadata(self, device_id: str) -> AgentMetadata | None:
        """Get agent metadata."""
        with self._manager_lock:
            return self._metadata.get(device_id)

    def register_abort_handler(
        self,
        device_id: str,
        abort_handler: threading.Event
        | Callable[[], None]
        | Callable[[], Awaitable[None]],
    ) -> None:
        """注册取消处理器 (支持同步和异步处理器)。

        Instantaneous operation (microsecond lock hold). Safe to call directly
        from async contexts without ``asyncio.to_thread``.

        Args:
            device_id: 设备标识符
            abort_handler: 取消处理器 (Event / 同步函数 / 异步函数)
        """
        with self._manager_lock:
            metadata = self._metadata.get(device_id)
            if metadata:
                metadata.abort_handler = abort_handler

    def unregister_abort_handler(self, device_id: str) -> None:
        """注销取消处理器。

        Instantaneous operation (microsecond lock hold). Safe to call directly
        from async ``finally`` blocks without ``asyncio.to_thread``.

        Args:
            device_id: 设备标识符
        """
        with self._manager_lock:
            metadata = self._metadata.get(device_id)
            if metadata:
                metadata.abort_handler = None

    async def abort_streaming_chat_async(self, device_id: str) -> bool:
        """异步中止流式对话 (支持 AsyncAgent)。

        Args:
            device_id: 设备标识符

        Returns:
            bool: True 表示发送了中止信号，False 表示没有活跃会话
        """
        with self._manager_lock:
            metadata = self._metadata.get(device_id)
            if not metadata or metadata.abort_handler is None:
                logger.warning(f"No active streaming chat for device {device_id}")
                return False

            logger.info(f"Aborting async streaming chat for device {device_id}")
            handler = metadata.abort_handler

        # 执行取消 (根据类型选择方式, 在锁外执行避免死锁)
        if isinstance(handler, threading.Event):
            handler.set()
        elif asyncio.iscoroutinefunction(handler):
            await handler()
        elif callable(handler):
            handler()
        else:
            logger.warning(f"Unknown abort handler type: {type(handler)}")
            return False

        return True

    def is_streaming_active(self, device_id: str) -> bool:
        """检查设备是否有活跃的流式会话."""
        with self._manager_lock:
            metadata = self._metadata.get(device_id)
            return metadata is not None and metadata.abort_handler is not None
