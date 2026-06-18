"""Agent lifecycle and concurrency manager (singleton)."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from AutoGLM_GUI.agents.protocols import AsyncAgent
from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.exceptions import (
    AgentInitializationError,
    AgentNotInitializedError,
    DeviceBusyError,
)
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.trace import trace_span
from AutoGLM_GUI.types import AgentSpecificConfig

T = TypeVar("T")


class _AsyncLock:
    """Async-compatible lock backed by threading.Lock.

    asyncio.Lock is bound to the event loop that creates it, which breaks
    singletons accessed from multiple event loops (e.g. FastAPI threadpool
    workers). This lock uses a plain threading.Lock so it works from both
    sync and async contexts without event-loop binding issues.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    async def acquire(self) -> bool:
        # Busy-wait with yields instead of blocking a worker thread. This avoids
        # deadlocking when the lock is held by async code that itself needs
        # worker threads (e.g. asyncio.to_thread for ADB/device operations).
        while not self._lock.acquire(blocking=False):
            await asyncio.sleep(0.001)
        return True

    def release(self) -> None:
        self._lock.release()

    async def __aenter__(self) -> _AsyncLock:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        self.release()
        return False

    def __enter__(self) -> _AsyncLock:
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        self.release()
        return False


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
    - Single async-compatible lock (_manager_lock) for all state transitions
    - No long-held per-device locks; acquire/release are instantaneous CAS operations
    - Context managers for automatic state release

    Example:
        >>> manager = PhoneAgentManager.get_instance()
        >>>
        >>> # Use agent with automatic locking (auto-initializes if needed)
        >>> async with manager.use_agent_async(device_id) as agent:
        >>>     result = await agent.run("Open WeChat")
    """

    _instance: PhoneAgentManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self):
        """Private constructor. Use get_instance() instead."""
        # Manager-level lock (protects internal state)
        # All state transitions (IDLE↔BUSY) are guarded by this single lock.
        # Each critical section holds it for microseconds only (atomic CAS),
        # so no asyncio.to_thread() wrapper is needed for release/register/unregister.
        self._manager_lock = _AsyncLock()

        # Agent metadata (indexed by device_id)
        # State is stored in AgentMetadata.state (single source of truth)
        self._metadata: dict[str, AgentMetadata] = {}

        # Agent storage (transition from global state to instance state)
        self._agents: dict[str, AsyncAgent] = {}
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

    # ==================== Lock helpers ====================

    def _run_sync(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run an async implementation coroutine from a sync context."""
        try:
            return asyncio.run(coro)
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                # Fallback: run in a worker thread with its own event loop.
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, coro).result()
            raise

    # ==================== Agent Lifecycle ====================

    async def _initialize_agent_with_factory_impl(
        self,
        device_id: str,
        agent_type: str,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        agent_specific_config: AgentSpecificConfig,
        takeover_callback: Callable[..., Any] | None = None,
        confirmation_callback: Callable[..., Any] | None = None,
        force: bool = False,
    ) -> AsyncAgent:
        with trace_span(
            "agent_manager.initialize_agent",
            attrs={
                "device_id": device_id,
                "agent_type": agent_type,
                "force": force,
            },
        ):
            agent: AsyncAgent | None = None
            async with self._manager_lock:
                agent = await self._initialize_agent_with_factory_unsafe(
                    device_id=device_id,
                    agent_type=agent_type,
                    model_config=model_config,
                    agent_config=agent_config,
                    agent_specific_config=agent_specific_config,
                    takeover_callback=takeover_callback,
                    confirmation_callback=confirmation_callback,
                    force=force,
                )
            assert agent is not None
            return agent

    async def _initialize_agent_with_factory_unsafe(
        self,
        device_id: str,
        agent_type: str,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        agent_specific_config: AgentSpecificConfig,
        takeover_callback: Callable[..., Any] | None = None,
        confirmation_callback: Callable[..., Any] | None = None,
        force: bool = False,
    ) -> AsyncAgent:
        """Actual initialization logic; caller must hold ``_manager_lock``."""
        from AutoGLM_GUI.agents import create_agent

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
            actual_device_id = agent_config.device_id
            if not actual_device_id:
                raise AgentInitializationError(
                    "agent_config.device_id is required but was None"
                )
            try:
                with trace_span(
                    "agent_manager.get_device_protocol",
                    attrs={"device_id": actual_device_id},
                ):
                    device = device_manager.get_async_device_protocol(actual_device_id)
            except ValueError:
                device_manager.force_refresh()
                with trace_span(
                    "agent_manager.get_device_protocol",
                    attrs={
                        "device_id": actual_device_id,
                        "after_refresh": True,
                    },
                ):
                    device = device_manager.get_async_device_protocol(actual_device_id)

            with trace_span(
                "agent_manager.create_agent",
                attrs={"device_id": device_id, "agent_type": agent_type},
            ):
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

    def initialize_agent_with_factory(
        self,
        device_id: str,
        agent_type: str,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        agent_specific_config: AgentSpecificConfig,
        takeover_callback: Callable[..., Any] | None = None,
        confirmation_callback: Callable[..., Any] | None = None,
        force: bool = False,
    ) -> AsyncAgent:
        return self._run_sync(
            self._initialize_agent_with_factory_impl(
                device_id=device_id,
                agent_type=agent_type,
                model_config=model_config,
                agent_config=agent_config,
                agent_specific_config=agent_specific_config,
                takeover_callback=takeover_callback,
                confirmation_callback=confirmation_callback,
                force=force,
            )
        )

    async def initialize_agent_with_factory_async(
        self,
        device_id: str,
        agent_type: str,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        agent_specific_config: AgentSpecificConfig,
        takeover_callback: Callable[..., Any] | None = None,
        confirmation_callback: Callable[..., Any] | None = None,
        force: bool = False,
    ) -> AsyncAgent:
        return await self._initialize_agent_with_factory_impl(
            device_id=device_id,
            agent_type=agent_type,
            model_config=model_config,
            agent_config=agent_config,
            agent_specific_config=agent_specific_config,
            takeover_callback=takeover_callback,
            confirmation_callback=confirmation_callback,
            force=force,
        )

    async def _auto_initialize_agent_impl(
        self, agent_key: str, actual_device_id: str, agent_type: str | None = None
    ) -> None:
        """
        使用全局配置自动初始化 agent.

        使用 factory 模式创建 agent，避免直接依赖 phone_agent.PhoneAgent。
        此方法会自行获取 ``_manager_lock``，适用于未持有锁的调用方。

        Args:
            agent_key: Agent 存储键（可能是 device_id 或 device_id:context）
            actual_device_id: 实际设备标识符（用于设备操作）
            agent_type: 可选的 agent 类型覆盖

        Raises:
            AgentInitializationError: 如果配置不完整或初始化失败
        """
        async with self._manager_lock:
            await self._auto_initialize_agent_unsafe(
                agent_key, actual_device_id, agent_type=agent_type
            )

    async def _auto_initialize_agent_unsafe(
        self, agent_key: str, actual_device_id: str, agent_type: str | None = None
    ) -> None:
        """
        使用全局配置自动初始化 agent（内部方法，调用方必须已持有 ``_manager_lock``）。

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

        # Web模式下使用空回调函数，不阻塞CLI
        # 前端会通过事件流检测交互action并处理用户输入
        def noop_takeover(message: str) -> None:
            logger.info(f"Takeover action (Web mode): {message}")
            # 不阻塞，让前端处理

        def noop_confirmation(message: str) -> bool:
            logger.info(f"Confirmation action (Web mode): {message}")
            # 在Web模式下默认确认，让前端处理
            return True

        await self._initialize_agent_with_factory_unsafe(
            device_id=agent_key,
            agent_type=effective_agent_type,
            model_config=model_config,
            agent_config=agent_config,
            agent_specific_config=agent_specific_config,
            takeover_callback=noop_takeover,
            confirmation_callback=noop_confirmation,
        )
        logger.info(f"Agent auto-initialized for key {agent_key}")

    def _auto_initialize_agent(
        self, agent_key: str, actual_device_id: str, agent_type: str | None = None
    ) -> None:
        return self._run_sync(
            self._auto_initialize_agent_impl(agent_key, actual_device_id, agent_type)
        )

    async def _get_agent_impl(self, device_id: str) -> AsyncAgent:
        return await self._get_agent_with_context_impl(device_id, context="default")

    def get_agent(self, device_id: str) -> AsyncAgent:
        """Get agent using default context (backward compatible)."""
        return self._run_sync(self._get_agent_impl(device_id))

    async def get_agent_async(self, device_id: str) -> AsyncAgent:
        return await self._get_agent_impl(device_id)

    async def _get_agent_with_context_impl(
        self,
        device_id: str,
        context: str = "default",
        agent_type: str | None = None,
    ) -> AsyncAgent:
        """Get or create agent for specific context.

        Args:
            device_id: Device identifier
            context: Context identifier (e.g., "chat", "default")
            agent_type: Optional agent type override

        Returns:
            Agent instance for this device+context combination
        """
        agent: AsyncAgent | None = None
        async with self._manager_lock:
            agent_key = self._make_agent_key(device_id, context)

            if agent_key not in self._agents:
                await self._auto_initialize_agent_unsafe(
                    agent_key, device_id, agent_type=agent_type
                )

            agent = self._agents[agent_key]
        assert agent is not None
        return agent

    def get_agent_with_context(
        self,
        device_id: str,
        context: str = "default",
        agent_type: str | None = None,
    ) -> AsyncAgent:
        return self._run_sync(
            self._get_agent_with_context_impl(device_id, context, agent_type)
        )

    async def get_agent_with_context_async(
        self,
        device_id: str,
        context: str = "default",
        agent_type: str | None = None,
    ) -> AsyncAgent:
        return await self._get_agent_with_context_impl(device_id, context, agent_type)

    async def _get_agent_safe_impl(self, device_id: str) -> AsyncAgent | None:
        async with self._manager_lock:
            return self._agents.get(device_id)

    def get_agent_safe(self, device_id: str) -> AsyncAgent | None:
        return self._run_sync(self._get_agent_safe_impl(device_id))

    async def _reset_agent_impl(self, device_id: str, context: str = "default") -> None:
        """
        Reset agent state by calling the agent's reset() method.

        Args:
            device_id: Device identifier
            context: Agent context (default, chat:session_id, scheduled, etc.)

        Raises:
            AgentNotInitializedError: If agent not initialized
        """
        agent_key = self._make_agent_key(device_id, context)
        async with self._manager_lock:
            if agent_key not in self._agents:
                raise AgentNotInitializedError(
                    f"Agent not initialized for device {device_id} (context={context})"
                )

            # Reset agent state using its reset() method
            self._agents[agent_key].reset()

            # Update metadata
            if agent_key in self._metadata:
                self._metadata[agent_key].last_used = time.time()
                self._metadata[agent_key].error_message = None
                self._metadata[agent_key].state = AgentState.IDLE

            logger.info(f"Agent reset for device {device_id} (context={context})")

    def reset_agent(self, device_id: str, context: str = "default") -> None:
        return self._run_sync(self._reset_agent_impl(device_id, context))

    async def reset_agent_async(self, device_id: str, context: str = "default") -> None:
        await self._reset_agent_impl(device_id, context)

    async def _destroy_agent_impl(
        self, device_id: str, context: str = "default"
    ) -> None:
        """
        Destroy agent and clean up resources.

        Args:
            device_id: Device identifier
            context: Agent context (default, chat:session_id, scheduled, etc.)
        """
        agent_key = self._make_agent_key(device_id, context)
        async with self._manager_lock:
            # Remove agent
            agent = self._agents.pop(agent_key, None)
            if agent:
                try:
                    agent.reset()  # Clean up agent state
                except Exception as e:
                    logger.warning(f"Error resetting agent during destroy: {e}")

            # Remove config
            self._agent_configs.pop(agent_key, None)

            # Remove metadata
            self._metadata.pop(agent_key, None)

            logger.info(f"Agent destroyed for device {device_id} (context={context})")

    def destroy_agent(self, device_id: str, context: str = "default") -> None:
        return self._run_sync(self._destroy_agent_impl(device_id, context))

    async def destroy_agent_async(
        self, device_id: str, context: str = "default"
    ) -> None:
        await self._destroy_agent_impl(device_id, context)

    async def _is_initialized_impl(
        self, device_id: str, context: str = "default"
    ) -> bool:
        """Check if agent is initialized for device."""
        initialized = False
        async with self._manager_lock:
            agent_key = self._make_agent_key(device_id, context)
            initialized = agent_key in self._agents
        return initialized

    def is_initialized(self, device_id: str, context: str = "default") -> bool:
        return self._run_sync(self._is_initialized_impl(device_id, context))

    async def is_initialized_async(
        self, device_id: str, context: str = "default"
    ) -> bool:
        return await self._is_initialized_impl(device_id, context)

    # ==================== Concurrency Control ====================

    def _make_agent_key(self, device_id: str, context: str = "default") -> str:
        """Build composite key for device+context isolation."""
        return device_id if context == "default" else f"{device_id}:{context}"

    async def _acquire_device_impl(
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
        _ = timeout
        agent_key = self._make_agent_key(device_id, context)

        # Auto-initialization (if needed) and the CAS must happen under the same
        # lock acquisition. Releasing the lock between init and CAS creates a race
        # window where another task can destroy the agent, leaving us returning
        # ``True`` without ever setting the state to BUSY.
        async with self._manager_lock:
            if agent_key not in self._agents:
                if auto_initialize:
                    await self._auto_initialize_agent_unsafe(agent_key, device_id)
                else:
                    raise AgentNotInitializedError(
                        f"Agent not initialized for device {agent_key}. "
                        f"Use auto_initialize=True or call initialize_agent() first."
                    )

            metadata = self._metadata.get(agent_key)
            if metadata is None:
                # The agent was destroyed between init and lookup (should be rare).
                raise AgentNotInitializedError(
                    f"Agent metadata missing for {agent_key}. "
                    f"The agent may have been destroyed concurrently."
                )
            if metadata.state == AgentState.BUSY:
                if raise_on_timeout:
                    raise DeviceBusyError(
                        f"Device {agent_key} is busy, could not acquire lock"
                    )
                return False
            metadata.state = AgentState.BUSY
            metadata.last_used = time.time()

        logger.debug(f"Device lock acquired for {agent_key}")
        return True

    def acquire_device(
        self,
        device_id: str,
        auto_initialize: bool = False,
        timeout: float | None = None,
        raise_on_timeout: bool = True,
        context: str = "default",
    ) -> bool:
        return self._run_sync(
            self._acquire_device_impl(
                device_id,
                auto_initialize=auto_initialize,
                timeout=timeout,
                raise_on_timeout=raise_on_timeout,
                context=context,
            )
        )

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
            self._acquire_device_impl(
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
                    asyncio.get_running_loop().create_task(
                        self.release_device_async(device_id, context=context)
                    )
                except BaseException as e:
                    logger.error(
                        f"Failed to cleanup cancelled acquire for {device_id}: {e}"
                    )

            acquire_task.add_done_callback(_cleanup_cancelled_acquire)
            raise

    async def _release_device_impl(
        self, device_id: str, context: str = "default"
    ) -> None:
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
        async with self._manager_lock:
            metadata = self._metadata.get(agent_key)
            if metadata:
                # Only transition BUSY→IDLE; preserve ERROR state so callers
                # can observe failures.  ERROR must be explicitly cleared.
                if metadata.state == AgentState.BUSY:
                    metadata.state = AgentState.IDLE
                metadata.abort_handler = None

        logger.debug(f"Device lock released for {agent_key}")

    def release_device(self, device_id: str, context: str = "default") -> None:
        return self._run_sync(self._release_device_impl(device_id, context))

    async def release_device_async(
        self, device_id: str, context: str = "default"
    ) -> None:
        await self._release_device_impl(device_id, context)

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
            AsyncAgent: Agent instance

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

    @asynccontextmanager
    async def use_agent_async(
        self,
        device_id: str,
        timeout: float | None = None,
        auto_initialize: bool = True,
    ):
        """Async context manager for automatic lock acquisition/release."""
        _ = timeout
        acquired = False
        try:
            acquired = await self.acquire_device_async(
                device_id,
                auto_initialize=auto_initialize,
            )
            agent = await self.get_agent_async(device_id)
            yield agent
        except Exception as exc:
            await self.set_error_state_async(device_id, str(exc))
            raise
        finally:
            if acquired:
                await self.release_device_async(device_id)

    # ==================== State Management ====================

    async def _get_state_impl(self, device_id: str) -> AgentState:
        """Get current agent state."""
        state = AgentState.ERROR
        async with self._manager_lock:
            metadata = self._metadata.get(device_id)
            state = metadata.state if metadata else AgentState.ERROR
        return state

    def get_state(self, device_id: str) -> AgentState:
        return self._run_sync(self._get_state_impl(device_id))

    async def get_state_async(self, device_id: str) -> AgentState:
        return await self._get_state_impl(device_id)

    async def _set_error_state_impl(
        self, device_id: str, error_message: str, context: str = "default"
    ) -> None:
        """Mark agent as errored."""
        agent_key = self._make_agent_key(device_id, context)
        async with self._manager_lock:
            if agent_key in self._metadata:
                self._metadata[agent_key].state = AgentState.ERROR
                self._metadata[agent_key].error_message = error_message

            logger.error(
                f"Agent error for {device_id} (context={context}): {error_message}"
            )

    def set_error_state(
        self, device_id: str, error_message: str, context: str = "default"
    ) -> None:
        return self._run_sync(
            self._set_error_state_impl(device_id, error_message, context)
        )

    async def set_error_state_async(
        self, device_id: str, error_message: str, context: str = "default"
    ) -> None:
        await self._set_error_state_impl(device_id, error_message, context)

    # ==================== Configuration Management ====================

    async def _get_config_impl(self, device_id: str) -> tuple[ModelConfig, AgentConfig]:
        """Get cached configuration for device."""
        config: tuple[ModelConfig, AgentConfig] | None = None
        async with self._manager_lock:
            if device_id not in self._agent_configs:
                raise AgentNotInitializedError(
                    f"No configuration found for device {device_id}"
                )
            config = self._agent_configs[device_id]
        assert config is not None
        return config

    def get_config(self, device_id: str) -> tuple[ModelConfig, AgentConfig]:
        return self._run_sync(self._get_config_impl(device_id))

    async def get_config_async(self, device_id: str) -> tuple[ModelConfig, AgentConfig]:
        return await self._get_config_impl(device_id)

    # ==================== Introspection ====================

    async def _list_agents_impl(self) -> list[str]:
        """Get list of all initialized device IDs."""
        agent_ids: list[str] = []
        async with self._manager_lock:
            agent_ids = list(self._agents.keys())
        return agent_ids

    def list_agents(self) -> list[str]:
        return self._run_sync(self._list_agents_impl())

    async def list_agents_async(self) -> list[str]:
        return await self._list_agents_impl()

    async def _get_metadata_impl(self, device_id: str) -> AgentMetadata | None:
        """Get agent metadata."""
        async with self._manager_lock:
            return self._metadata.get(device_id)

    def get_metadata(self, device_id: str) -> AgentMetadata | None:
        return self._run_sync(self._get_metadata_impl(device_id))

    async def get_metadata_async(self, device_id: str) -> AgentMetadata | None:
        return await self._get_metadata_impl(device_id)

    async def _get_metadata_for_device_impl(
        self, device_id: str
    ) -> AgentMetadata | None:
        """Get the most relevant metadata for a device across all contexts.

        Device-level UI cares whether a device has any initialized agent, even when
        the runtime agent is stored under a contextual key such as
        ``device_id:chat:<session_id>``.
        """
        state_priority = {
            AgentState.BUSY: 4,
            AgentState.INITIALIZING: 3,
            AgentState.ERROR: 2,
            AgentState.IDLE: 1,
        }
        key_prefix = f"{device_id}:"
        candidates: list[AgentMetadata] = []

        async with self._manager_lock:
            candidates = [
                metadata
                for key, metadata in self._metadata.items()
                if key == device_id or key.startswith(key_prefix)
            ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda metadata: (
                state_priority.get(metadata.state, 0),
                metadata.last_used,
                metadata.created_at,
            ),
        )

    def get_metadata_for_device(self, device_id: str) -> AgentMetadata | None:
        return self._run_sync(self._get_metadata_for_device_impl(device_id))

    async def get_metadata_for_device_async(
        self, device_id: str
    ) -> AgentMetadata | None:
        return await self._get_metadata_for_device_impl(device_id)

    async def _get_metadata_snapshot_impl(self) -> dict[str, AgentMetadata]:
        """Return a shallow copy of the metadata map under the manager lock."""
        snapshot: dict[str, AgentMetadata] = {}
        async with self._manager_lock:
            snapshot = dict(self._metadata)
        return snapshot

    def get_metadata_snapshot(self) -> dict[str, AgentMetadata]:
        return self._run_sync(self._get_metadata_snapshot_impl())

    async def _get_streaming_sessions_count_impl(self) -> int:
        count = 0
        async with self._manager_lock:
            count = sum(
                1 for m in self._metadata.values() if m.abort_handler is not None
            )
        return count

    def get_streaming_sessions_count(self) -> int:
        return self._run_sync(self._get_streaming_sessions_count_impl())

    async def _register_abort_handler_impl(
        self,
        device_id: str,
        abort_handler: threading.Event
        | Callable[[], None]
        | Callable[[], Awaitable[None]],
        context: str = "default",
    ) -> None:
        """注册取消处理器 (支持同步和异步处理器).

        Instantaneous operation (microsecond lock hold). Safe to call directly
        from async contexts without ``asyncio.to_thread``.

        Args:
            device_id: 设备标识符
            abort_handler: 取消处理器 (Event / 同步函数 / 异步函数)
        """
        async with self._manager_lock:
            metadata = self._metadata.get(self._make_agent_key(device_id, context))
            if metadata:
                metadata.abort_handler = abort_handler

    def register_abort_handler(
        self,
        device_id: str,
        abort_handler: threading.Event
        | Callable[[], None]
        | Callable[[], Awaitable[None]],
        context: str = "default",
    ) -> None:
        return self._run_sync(
            self._register_abort_handler_impl(device_id, abort_handler, context)
        )

    async def register_abort_handler_async(
        self,
        device_id: str,
        abort_handler: threading.Event
        | Callable[[], None]
        | Callable[[], Awaitable[None]],
        context: str = "default",
    ) -> None:
        await self._register_abort_handler_impl(device_id, abort_handler, context)

    async def _unregister_abort_handler_impl(
        self, device_id: str, context: str = "default"
    ) -> None:
        """注销取消处理器.

        Instantaneous operation (microsecond lock hold). Safe to call directly
        from async ``finally`` blocks without ``asyncio.to_thread``.

        Args:
            device_id: 设备标识符
        """
        async with self._manager_lock:
            metadata = self._metadata.get(self._make_agent_key(device_id, context))
            if metadata:
                metadata.abort_handler = None

    def unregister_abort_handler(
        self, device_id: str, context: str = "default"
    ) -> None:
        return self._run_sync(self._unregister_abort_handler_impl(device_id, context))

    async def unregister_abort_handler_async(
        self, device_id: str, context: str = "default"
    ) -> None:
        await self._unregister_abort_handler_impl(device_id, context)

    async def abort_streaming_chat_async(self, device_id: str) -> bool:
        """异步中止流式对话 (支持 AsyncAgent)。

        搜索所有与 device_id 相关的 contextual key（如
        ``device_id:chat:session_id``），找到拥有 abort handler 的 agent
        并调用其取消逻辑。

        Args:
            device_id: 设备标识符

        Returns:
            bool: True 表示发送了中止信号，False 表示没有活跃会话
        """
        handler: Any = None
        has_candidates = False
        async with self._manager_lock:
            # 查找所有匹配的 contextual key，优先选择有 abort handler 的
            key_prefix = f"{device_id}:"
            candidates: list[tuple[str, Any]] = []
            for key, metadata in self._metadata.items():
                if (
                    key == device_id or key.startswith(key_prefix)
                ) and metadata.abort_handler is not None:
                    candidates.append((key, metadata.abort_handler))

            if candidates:
                has_candidates = True
                # 优先使用精确匹配
                for key, h in candidates:
                    handler = h
                    if key == device_id:
                        break

                logger.info(
                    f"Aborting async streaming chat for device {device_id} "
                    f"(found {len(candidates)} active handler(s))"
                )
            else:
                logger.warning(f"No active streaming chat for device {device_id}")

        if not has_candidates:
            return False

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

    async def _is_streaming_active_impl(self, device_id: str) -> bool:
        """检查设备是否有活跃的流式会话."""
        active = False
        async with self._manager_lock:
            key_prefix = f"{device_id}:"
            for key, metadata in self._metadata.items():
                if (
                    key == device_id or key.startswith(key_prefix)
                ) and metadata.abort_handler is not None:
                    active = True
                    break
        return active

    def is_streaming_active(self, device_id: str) -> bool:
        return self._run_sync(self._is_streaming_active_impl(device_id))

    async def is_streaming_active_async(self, device_id: str) -> bool:
        return await self._is_streaming_active_impl(device_id)

    async def _destroy_all_agents_impl(self) -> int:
        """销毁所有 Agent 实例，用于配置热更新.

        Returns:
            int: 销毁的 Agent 数量
        """
        count = 0
        async with self._manager_lock:
            agent_keys = list(self._agents.keys())
            count = len(agent_keys)

            for agent_key in agent_keys:
                agent = self._agents.pop(agent_key, None)
                if agent:
                    try:
                        agent.reset()  # Clean up agent state
                    except Exception as e:
                        logger.warning(
                            f"Error resetting agent {agent_key} during destroy_all: {e}"
                        )

                # Remove config and metadata
                self._agent_configs.pop(agent_key, None)
                self._metadata.pop(agent_key, None)

            if count > 0:
                logger.info(f"Destroyed {count} agent(s) for config hot reload")

        return count

    def destroy_all_agents(self) -> int:
        return self._run_sync(self._destroy_all_agents_impl())

    async def destroy_all_agents_async(self) -> int:
        return await self._destroy_all_agents_impl()
