"""Task orchestration and execution."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, cast

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.task_store import (
    TERMINAL_TASK_STATUSES,
    TaskRecord,
    TaskSessionRecord,
    TaskStatus,
    TaskStore,
    task_store,
)

TaskExecutor = Callable[[TaskRecord], Awaitable[None]]


class TaskManager:
    """Queue-backed task manager with per-device workers."""

    def __init__(self, store: TaskStore = task_store):
        self.store = store
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._abort_handlers: dict[
            str, Callable[[], Any] | Callable[[], Awaitable[Any]]
        ] = {}
        self._completion_events: dict[str, asyncio.Event] = {}
        self._cancel_requested: set[str] = set()
        self._executors: dict[str, TaskExecutor] = {}
        self._started = False
        self._shutdown = False
        self.register_executor("classic_chat", self._execute_classic_chat)
        self.register_executor("scheduled_workflow", self._execute_scheduled_workflow)

    def register_executor(self, executor_key: str, executor: TaskExecutor) -> None:
        self._executors[executor_key] = executor

    async def start(self) -> None:
        if self._started:
            return
        self._shutdown = False
        interrupted = await asyncio.to_thread(self.store.mark_running_tasks_interrupted)
        if interrupted:
            logger.warning(f"Recovered {interrupted} interrupted task(s)")
        for device_id in await asyncio.to_thread(self.store.get_queued_device_ids):
            self._ensure_worker(device_id)
        self._started = True

    async def shutdown(self) -> None:
        self._shutdown = True
        workers = list(self._workers.values())
        self._workers.clear()
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._started = False

    async def create_chat_session(
        self, *, device_id: str, device_serial: str
    ) -> TaskSessionRecord:
        return await asyncio.to_thread(
            self.store.create_session,
            kind="chat",
            mode="classic",
            device_id=device_id,
            device_serial=device_serial,
        )

    async def get_session(self, session_id: str) -> TaskSessionRecord | None:
        return await asyncio.to_thread(self.store.get_session, session_id)

    async def get_or_create_legacy_chat_session(
        self, *, device_id: str, device_serial: str
    ) -> TaskSessionRecord:
        session = await asyncio.to_thread(
            self.store.get_latest_open_chat_session,
            device_id=device_id,
            device_serial=device_serial,
        )
        if session:
            return session
        return await self.create_chat_session(
            device_id=device_id,
            device_serial=device_serial,
        )

    async def submit_chat_task(
        self,
        *,
        session_id: str,
        device_id: str,
        device_serial: str,
        message: str,
    ) -> TaskRecord:
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        task = await asyncio.to_thread(
            self.store.create_task_run,
            source="chat",
            executor_key="classic_chat",
            session_id=session_id,
            device_id=device_id,
            device_serial=device_serial,
            input_text=message,
        )
        self._completion_events[task["id"]] = asyncio.Event()
        self._ensure_worker(device_id)
        return task

    async def enqueue_scheduled_task(
        self,
        *,
        scheduled_task_id: str,
        workflow_uuid: str,
        device_id: str,
        device_serial: str,
        input_text: str,
        schedule_fire_id: str,
    ) -> TaskRecord:
        task = await asyncio.to_thread(
            self.store.create_task_run,
            source="scheduled",
            executor_key="scheduled_workflow",
            scheduled_task_id=scheduled_task_id,
            workflow_uuid=workflow_uuid,
            schedule_fire_id=schedule_fire_id,
            device_id=device_id,
            device_serial=device_serial,
            input_text=input_text,
        )
        self._completion_events[task["id"]] = asyncio.Event()
        self._ensure_worker(device_id)
        return task

    async def wait_for_task(
        self, task_id: str, timeout: float | None = None
    ) -> TaskRecord | None:
        task = await asyncio.to_thread(self.store.get_task, task_id)
        if task is None:
            return None
        if task["status"] in TERMINAL_TASK_STATUSES:
            return task

        event = self._completion_events.setdefault(task_id, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            return await asyncio.to_thread(self.store.get_task, task_id)
        return await asyncio.to_thread(self.store.get_task, task_id)

    async def cancel_task(self, task_id: str) -> TaskRecord | None:
        task = await asyncio.to_thread(self.store.get_task, task_id)
        if task is None:
            return None

        status = task["status"]
        if status in TERMINAL_TASK_STATUSES:
            return task

        if status == TaskStatus.QUEUED.value:
            updated = await asyncio.to_thread(self.store.cancel_queued_task, task_id)
            if updated:
                self._mark_task_complete(task_id)
            return updated

        if status == TaskStatus.RUNNING.value:
            self._cancel_requested.add(task_id)
            handler = self._abort_handlers.get(task_id)
            if handler is not None:
                result = handler()
                if inspect.isawaitable(result):
                    await result
            return await asyncio.to_thread(self.store.get_task, task_id)

        return task

    async def cancel_latest_chat_task(self, device_id: str) -> TaskRecord | None:
        task = await asyncio.to_thread(
            self.store.get_latest_active_chat_task, device_id
        )
        if task is None:
            return None
        return await self.cancel_task(task["id"])

    def _ensure_worker(self, device_id: str) -> None:
        if self._shutdown:
            return
        worker = self._workers.get(device_id)
        if worker is None or worker.done():
            self._workers[device_id] = asyncio.create_task(
                self._device_worker(device_id),
                name=f"TaskWorker-{device_id}",
            )

    @staticmethod
    def _register_abort_handler(
        manager: Any,
        device_id: str,
        handler: Callable[[], Any] | Callable[[], Awaitable[Any]],
        *,
        context: str,
    ) -> None:
        try:
            manager.register_abort_handler(device_id, handler, context=context)
        except TypeError:
            manager.register_abort_handler(device_id, handler)

    @staticmethod
    def _unregister_abort_handler(
        manager: Any,
        device_id: str,
        *,
        context: str,
    ) -> None:
        try:
            manager.unregister_abort_handler(device_id, context=context)
        except TypeError:
            manager.unregister_abort_handler(device_id)

    async def _device_worker(self, device_id: str) -> None:
        try:
            while not self._shutdown:
                task = await asyncio.to_thread(
                    self.store.claim_next_queued_task, device_id
                )
                if task is None:
                    break

                executor = self._executors.get(task["executor_key"])
                if executor is None:
                    await self._fail_task(
                        task,
                        f"Unsupported executor: {task['executor_key']}",
                    )
                    continue

                try:
                    await executor(task)
                except asyncio.CancelledError:
                    if task["id"] not in self._cancel_requested:
                        await self._interrupt_task(
                            task,
                            "Task interrupted because the service shut down",
                        )
                    raise
                except Exception as exc:  # pragma: no cover - safety net
                    logger.exception(f"Task {task['id']} crashed unexpectedly")
                    await self._fail_task(task, str(exc))
        finally:
            self._workers.pop(device_id, None)

    async def _execute_classic_chat(self, task: TaskRecord) -> None:
        from AutoGLM_GUI.agents.protocols import is_async_agent
        from AutoGLM_GUI.exceptions import AgentInitializationError, DeviceBusyError
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
        from AutoGLM_GUI.trace import (
            create_trace_id,
            get_step_timing_summary,
            trace_context,
        )

        manager = PhoneAgentManager.get_instance()
        task_id = task["id"]
        device_id = task["device_id"]
        session_id = task["session_id"] or task_id
        context = f"chat:{session_id}"
        trace_id = create_trace_id()
        acquired = False
        final_status = TaskStatus.FAILED.value
        final_message = ""
        step_count = 0
        abort_registered = False

        try:
            with trace_context(trace_id):
                acquired = await manager.acquire_device_async(
                    device_id,
                    auto_initialize=True,
                    context=context,
                )
                agent = await asyncio.to_thread(
                    manager.get_agent_with_context,
                    device_id,
                    context=context,
                    agent_type=None,
                )

                async def cancel_handler() -> None:
                    if is_async_agent(agent):
                        await agent.cancel()  # type: ignore[union-attr]
                    else:
                        abort = getattr(agent, "abort", None)
                        if callable(abort):
                            await asyncio.to_thread(abort)

                self._abort_handlers[task_id] = cancel_handler
                self._register_abort_handler(
                    manager,
                    device_id,
                    cancel_handler,
                    context=context,
                )
                abort_registered = True

                if is_async_agent(agent):
                    async for event in agent.stream(task["input_text"]):  # type: ignore[union-attr]
                        event_type = event["type"]
                        event_data = dict(event.get("data", {}))

                        if event_type == "step":
                            step_count = max(step_count, int(event_data.get("step", 0)))
                            timings = get_step_timing_summary(
                                step_count,
                                trace_id=trace_id,
                            )
                            if timings is not None:
                                event_data = {**event_data, "timings": timings}

                        await asyncio.to_thread(
                            self.store.append_event,
                            task_id=task_id,
                            event_type=event_type,
                            payload=event_data,
                            role="assistant",
                        )

                        if event_type == "done":
                            final_message = str(event_data.get("message", ""))
                            final_status = (
                                TaskStatus.SUCCEEDED.value
                                if event_data.get("success", False)
                                else TaskStatus.FAILED.value
                            )
                            step_count = int(event_data.get("steps", step_count))
                        elif event_type == "error":
                            final_message = str(
                                event_data.get("message", "Task failed")
                            )
                            final_status = TaskStatus.FAILED.value
                        elif event_type == "cancelled":
                            final_message = str(
                                event_data.get("message", "Task cancelled by user")
                            )
                            final_status = TaskStatus.CANCELLED.value
                else:
                    sync_agent = cast(Any, agent)
                    result = await asyncio.to_thread(sync_agent.run, task["input_text"])
                    step_count = int(sync_agent.step_count)
                    final_message = str(result)
                    final_status = TaskStatus.SUCCEEDED.value

            if not final_message:
                final_message = "Task finished without a final response"
                final_status = TaskStatus.FAILED.value
        except asyncio.CancelledError:
            if task_id in self._cancel_requested:
                final_message = "Task cancelled by user"
                final_status = TaskStatus.CANCELLED.value
                await asyncio.to_thread(
                    self.store.append_event,
                    task_id=task_id,
                    event_type="cancelled",
                    payload={"message": final_message},
                    role="assistant",
                )
                await self._finalize_task(
                    task_id=task_id,
                    status=final_status,
                    final_message=final_message,
                    step_count=step_count,
                )
                return
            raise
        except DeviceBusyError:
            final_message = f"Device {device_id} is busy. Please wait."
            final_status = TaskStatus.FAILED.value
            await asyncio.to_thread(
                self.store.append_event,
                task_id=task_id,
                event_type="error",
                payload={"message": final_message},
                role="assistant",
            )
        except AgentInitializationError as exc:
            final_message = (
                f"初始化失败: {exc}. 请检查全局配置 (base_url, api_key, model_name)"
            )
            final_status = TaskStatus.FAILED.value
            await asyncio.to_thread(
                self.store.append_event,
                task_id=task_id,
                event_type="error",
                payload={"message": final_message},
                role="assistant",
            )
        except Exception as exc:
            final_message = str(exc)
            final_status = TaskStatus.FAILED.value
            await asyncio.to_thread(
                self.store.append_event,
                task_id=task_id,
                event_type="error",
                payload={"message": final_message},
                role="assistant",
            )
        finally:
            self._cancel_requested.discard(task_id)
            self._abort_handlers.pop(task_id, None)
            if abort_registered:
                self._unregister_abort_handler(
                    manager,
                    device_id,
                    context=context,
                )
            if acquired:
                manager.release_device(device_id, context=context)

        await self._finalize_task(
            task_id=task_id,
            status=final_status,
            final_message=final_message,
            step_count=step_count,
        )

    async def _execute_scheduled_workflow(self, task: TaskRecord) -> None:
        from AutoGLM_GUI.agents.protocols import is_async_agent
        from AutoGLM_GUI.exceptions import AgentInitializationError, DeviceBusyError
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

        manager = PhoneAgentManager.get_instance()
        task_id = task["id"]
        device_id = task["device_id"]
        context = "scheduled"
        acquired = False
        final_status = TaskStatus.FAILED.value
        final_message = ""
        step_count = 0
        abort_registered = False

        try:
            acquired = await manager.acquire_device_async(
                device_id,
                auto_initialize=True,
                context=context,
            )
            agent = await asyncio.to_thread(
                manager.get_agent_with_context,
                device_id,
                context=context,
                agent_type=None,
            )

            async def cancel_handler() -> None:
                if is_async_agent(agent):
                    await agent.cancel()  # type: ignore[union-attr]

            self._abort_handlers[task_id] = cancel_handler
            self._register_abort_handler(
                manager,
                device_id,
                cancel_handler,
                context=context,
            )
            abort_registered = True
            agent.reset()

            if is_async_agent(agent):
                async for event in agent.stream(task["input_text"]):  # type: ignore[union-attr]
                    event_type = event["type"]
                    event_data = dict(event.get("data", {}))
                    if event_type == "thinking":
                        await asyncio.to_thread(
                            self.store.append_event,
                            task_id=task_id,
                            event_type="thinking",
                            payload=event_data,
                            role="assistant",
                        )
                    elif event_type == "step":
                        step_count = max(step_count, int(event_data.get("step", 0)))
                        await asyncio.to_thread(
                            self.store.append_event,
                            task_id=task_id,
                            event_type="step",
                            payload=event_data,
                            role="assistant",
                        )
                    elif event_type == "done":
                        final_message = str(event_data.get("message", "Task completed"))
                        final_status = (
                            TaskStatus.SUCCEEDED.value
                            if event_data.get("success", False)
                            else TaskStatus.FAILED.value
                        )
                        step_count = int(event_data.get("steps", step_count))
                    elif event_type == "error":
                        final_message = str(event_data.get("message", "Task failed"))
                        final_status = TaskStatus.FAILED.value
                        await asyncio.to_thread(
                            self.store.append_event,
                            task_id=task_id,
                            event_type="error",
                            payload={"message": final_message},
                            role="assistant",
                        )
            else:
                sync_agent = cast(Any, agent)
                is_first = True
                while sync_agent.step_count < sync_agent.agent_config.max_steps:
                    step_result = await asyncio.to_thread(
                        sync_agent.step,
                        task["input_text"] if is_first else None,
                    )
                    is_first = False
                    step_count = int(sync_agent.step_count)
                    await asyncio.to_thread(
                        self.store.append_event,
                        task_id=task_id,
                        event_type="step",
                        payload={
                            "step": step_count,
                            "thinking": step_result.thinking,
                            "action": step_result.action,
                            "success": step_result.success,
                            "finished": step_result.finished,
                        },
                        role="assistant",
                    )
                    if step_result.finished:
                        final_message = step_result.message or "Task completed"
                        final_status = (
                            TaskStatus.SUCCEEDED.value
                            if step_result.success
                            else TaskStatus.FAILED.value
                        )
                        break
                else:
                    final_message = "Max steps reached"
                    final_status = TaskStatus.FAILED.value

            if not final_message:
                final_message = "Task finished without a final response"
                final_status = TaskStatus.FAILED.value
        except asyncio.CancelledError:
            if task_id in self._cancel_requested:
                final_message = "Task cancelled by user"
                final_status = TaskStatus.CANCELLED.value
                await asyncio.to_thread(
                    self.store.append_event,
                    task_id=task_id,
                    event_type="cancelled",
                    payload={"message": final_message},
                    role="assistant",
                )
                await self._finalize_task(
                    task_id=task_id,
                    status=final_status,
                    final_message=final_message,
                    step_count=step_count,
                )
                return
            raise
        except DeviceBusyError:
            final_message = f"Device {device_id} is busy. Please wait."
            final_status = TaskStatus.FAILED.value
            await asyncio.to_thread(
                self.store.append_event,
                task_id=task_id,
                event_type="error",
                payload={"message": final_message},
                role="assistant",
            )
        except AgentInitializationError as exc:
            final_message = (
                f"初始化失败: {exc}. 请检查全局配置 (base_url, api_key, model_name)"
            )
            final_status = TaskStatus.FAILED.value
            await asyncio.to_thread(
                self.store.append_event,
                task_id=task_id,
                event_type="error",
                payload={"message": final_message},
                role="assistant",
            )
        except Exception as exc:
            final_message = str(exc)
            final_status = TaskStatus.FAILED.value
            await asyncio.to_thread(
                self.store.append_event,
                task_id=task_id,
                event_type="error",
                payload={"message": final_message},
                role="assistant",
            )
        finally:
            self._cancel_requested.discard(task_id)
            self._abort_handlers.pop(task_id, None)
            if abort_registered:
                self._unregister_abort_handler(
                    manager,
                    device_id,
                    context=context,
                )
            if acquired:
                manager.release_device(device_id, context=context)

        await self._finalize_task(
            task_id=task_id,
            status=final_status,
            final_message=final_message,
            step_count=step_count,
        )

    async def _finalize_task(
        self,
        *,
        task_id: str,
        status: str,
        final_message: str,
        step_count: int,
    ) -> None:
        if status == TaskStatus.SUCCEEDED.value:
            event_type = "done"
            payload = {
                "message": final_message,
                "steps": step_count,
                "success": True,
            }
            error_message = None
        elif status == TaskStatus.CANCELLED.value:
            event_type = "cancelled"
            payload = {"message": final_message}
            error_message = final_message
        else:
            event_type = "error"
            payload = {"message": final_message}
            error_message = final_message

        existing_events = await asyncio.to_thread(self.store.list_task_events, task_id)
        if not any(event["event_type"] == event_type for event in existing_events):
            await asyncio.to_thread(
                self.store.append_event,
                task_id=task_id,
                event_type=event_type,
                payload=payload,
                role="assistant",
            )

        await asyncio.to_thread(
            self.store.update_task_terminal,
            task_id=task_id,
            status=status,
            final_message=final_message,
            error_message=error_message,
            step_count=step_count,
        )
        self._mark_task_complete(task_id)

    async def _fail_task(self, task: TaskRecord, message: str) -> None:
        await asyncio.to_thread(
            self.store.append_event,
            task_id=task["id"],
            event_type="error",
            payload={"message": message},
            role="assistant",
        )
        await self._finalize_task(
            task_id=task["id"],
            status=TaskStatus.FAILED.value,
            final_message=message,
            step_count=int(task.get("step_count", 0)),
        )

    async def _interrupt_task(self, task: TaskRecord, message: str) -> None:
        await asyncio.to_thread(
            self.store.append_event,
            task_id=task["id"],
            event_type="error",
            payload={"message": message},
            role="assistant",
        )
        await asyncio.to_thread(
            self.store.update_task_terminal,
            task_id=task["id"],
            status=TaskStatus.INTERRUPTED.value,
            final_message=message,
            error_message=message,
            step_count=int(task.get("step_count", 0)),
        )
        self._mark_task_complete(task["id"])

    def _mark_task_complete(self, task_id: str) -> None:
        event = self._completion_events.setdefault(task_id, asyncio.Event())
        event.set()


task_manager = TaskManager()
