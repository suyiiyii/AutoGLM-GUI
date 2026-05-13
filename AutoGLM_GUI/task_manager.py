"""Task orchestration and execution."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.metrics import record_trace_latency_metrics
from AutoGLM_GUI.task_store import (
    TERMINAL_TASK_STATUSES,
    TaskEventRecord,
    TaskRecord,
    TaskSessionRecord,
    TaskStatus,
    TaskStore,
    task_store,
)
import AutoGLM_GUI.trace as trace_module

TaskExecutor = Callable[[TaskRecord], Awaitable[None]]
TaskImageAttachment = dict[str, Any]


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
        self.register_executor("layered_chat", self._execute_layered_chat)
        self.register_executor("scheduled_workflow", self._execute_scheduled_workflow)
        self.register_executor(
            "scheduled_layered_workflow", self._execute_scheduled_layered_workflow
        )

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
        self, *, device_id: str, device_serial: str, mode: str = "classic"
    ) -> TaskSessionRecord:
        return await asyncio.to_thread(
            self.store.create_session,
            kind="chat",
            mode=mode,
            device_id=device_id,
            device_serial=device_serial,
        )

    async def get_session(self, session_id: str) -> TaskSessionRecord | None:
        return await asyncio.to_thread(self.store.get_session, session_id)

    async def get_or_create_legacy_chat_session(
        self, *, device_id: str, device_serial: str, mode: str = "classic"
    ) -> TaskSessionRecord:
        session = await asyncio.to_thread(
            self.store.get_latest_open_chat_session,
            device_id=device_id,
            device_serial=device_serial,
            mode=mode,
        )
        if session:
            return session
        return await self.create_chat_session(
            device_id=device_id,
            device_serial=device_serial,
            mode=mode,
        )

    async def archive_session(self, session_id: str) -> TaskSessionRecord | None:
        session = await self.get_session(session_id)
        if session is None:
            return None
        archived = await asyncio.to_thread(self.store.archive_session, session_id)
        if archived is not None:
            # Clean up the contextual agent for this session to prevent memory leak.
            # The agent key pattern is "device_id:chat:session_id".
            device_id = str(archived["device_id"])
            context = f"chat:{session_id}"
            try:
                from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

                manager = PhoneAgentManager.get_instance()
                manager.destroy_agent(device_id, context=context)
            except Exception as exc:
                logger.debug(
                    f"Contextual agent cleanup skipped for {device_id}/{context}: {exc}"
                )
        return archived

    async def submit_chat_task(
        self,
        *,
        session_id: str,
        device_id: str,
        device_serial: str,
        message: str,
        attachments: list[TaskImageAttachment] | None = None,
    ) -> TaskRecord:
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        session_mode = str(session["mode"])
        executor_key = {
            "classic": "classic_chat",
            "layered": "layered_chat",
        }.get(session_mode)
        if executor_key is None:
            raise ValueError(f"Unsupported session mode: {session_mode}")

        task = await asyncio.to_thread(
            self.store.create_task_run,
            source="chat",
            executor_key=executor_key,
            session_id=session_id,
            device_id=device_id,
            device_serial=device_serial,
            input_text=message,
        )
        await asyncio.to_thread(
            self.store.append_event,
            task_id=task["id"],
            event_type="user_message",
            role="user",
            payload={
                "message": message,
                "attachments": attachments or [],
            },
        )
        self._completion_events[task["id"]] = asyncio.Event()
        self._ensure_worker(device_id)
        return task

    def _get_task_user_image_attachments(
        self, task_id: str
    ) -> list[TaskImageAttachment]:
        events = self.store.list_task_events(task_id)
        for event in events:
            if event["event_type"] != "user_message":
                continue
            payload = event.get("payload", {})
            attachments = payload.get("attachments")
            if not isinstance(attachments, list):
                return []
            return [
                attachment
                for attachment in attachments
                if isinstance(attachment, dict)
                and isinstance(attachment.get("mime_type"), str)
                and isinstance(attachment.get("data"), str)
            ]
        return []

    async def enqueue_scheduled_task(
        self,
        *,
        scheduled_task_id: str,
        workflow_uuid: str,
        device_id: str,
        device_serial: str,
        input_text: str,
        schedule_fire_id: str,
        executor_key: str = "scheduled_workflow",
    ) -> TaskRecord:
        task = await asyncio.to_thread(
            self.store.create_task_run,
            source="scheduled",
            executor_key=executor_key,
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

    async def cancel_latest_chat_task(
        self, device_id: str, mode: str | None = None
    ) -> TaskRecord | None:
        task = await asyncio.to_thread(
            self.store.get_latest_active_chat_task, device_id, mode
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

    async def _record_trace_artifacts(
        self,
        *,
        task_id: str,
        trace_id: str,
        metrics_source: str,
        step_count: int,
        total_duration_ms: int,
    ) -> None:
        try:
            step_summaries = trace_module.list_step_timing_summaries(trace_id=trace_id)
            trace_summary_dict = trace_module.get_trace_timing_summary(
                trace_id=trace_id,
                total_duration_ms=total_duration_ms,
                steps=step_count,
            )
            if trace_summary_dict is not None:
                await self._append_task_event(
                    task_id=task_id,
                    event_type="trace_summary",
                    payload={
                        "summary": trace_summary_dict,
                        "step_summaries": step_summaries,
                    },
                    role="system",
                    trace_id=trace_id,
                    replay_source=metrics_source,
                )
            record_trace_latency_metrics(
                source=metrics_source,
                trace_summary=trace_summary_dict,
                step_summaries=step_summaries,
            )
        except Exception:
            logger.warning(
                "Failed to persist trace artifacts for task %s",
                task_id,
                exc_info=True,
            )

    async def _write_replay_task_start(
        self,
        *,
        task: TaskRecord,
        trace_id: str,
        source: str,
    ) -> None:
        replay_task = {**task, "trace_id": trace_id}
        await asyncio.to_thread(
            trace_module.write_replay_task_start,
            task_id=str(task["id"]),
            trace_id=trace_id,
            task=replay_task,
            source=source,
        )

    async def _append_task_event(
        self,
        *,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        role: str = "assistant",
        trace_id: str | None = None,
        replay_source: str | None = None,
        task: TaskRecord | None = None,
    ) -> TaskEventRecord:
        event_record = await asyncio.to_thread(
            self.store.append_event,
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            role=role,
        )
        if trace_id and replay_source:
            replay_task = task
            if replay_task is None:
                replay_task = await asyncio.to_thread(self.store.get_task, task_id)
            await asyncio.to_thread(
                trace_module.write_replay_event,
                task_id=task_id,
                trace_id=trace_id,
                event_record=event_record,
                source=replay_source,
                task=replay_task,
            )
        return event_record

    async def _finalize_traced_task(
        self,
        *,
        task_id: str,
        trace_id: str,
        status: str,
        final_message: str,
        stop_reason: str | None,
        step_count: int,
        metrics_source: str,
        start_perf: float,
    ) -> None:
        total_duration_ms = int((time.perf_counter() - start_perf) * 1000)
        try:
            with trace_module.trace_context(trace_id, reset_stack=False):
                await self._finalize_task(
                    task_id=task_id,
                    status=status,
                    final_message=final_message,
                    stop_reason=stop_reason,
                    step_count=step_count,
                    trace_id=trace_id,
                    mark_complete=False,
                    replay_source=metrics_source,
                )
                await self._record_trace_artifacts(
                    task_id=task_id,
                    trace_id=trace_id,
                    metrics_source=metrics_source,
                    step_count=step_count,
                    total_duration_ms=total_duration_ms,
                )
                self._mark_task_complete(task_id)
        finally:
            trace_module.clear_trace_data(trace_id)

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
        from AutoGLM_GUI.exceptions import AgentInitializationError, DeviceBusyError
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

        manager = PhoneAgentManager.get_instance()
        task_id = task["id"]
        device_id = task["device_id"]
        session_id = task["session_id"] or task_id
        context = f"chat:{session_id}"
        trace_id = trace_module.create_trace_id()
        start_perf = time.perf_counter()
        acquired = False
        final_status = TaskStatus.FAILED.value
        final_message = ""
        stop_reason = "error"
        step_count = 0
        abort_registered = False

        try:
            with trace_module.trace_context(trace_id):
                await asyncio.to_thread(self.store.set_task_trace_id, task_id, trace_id)
                await self._write_replay_task_start(
                    task=task,
                    trace_id=trace_id,
                    source="classic_chat",
                )
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
                user_image_attachments = await asyncio.to_thread(
                    self._get_task_user_image_attachments,
                    task_id,
                )
                image_attachment_setter: (
                    Callable[[list[TaskImageAttachment]], None] | None
                ) = None
                setter_candidate = getattr(agent, "set_user_image_attachments", None)
                if callable(setter_candidate):
                    image_attachment_setter = cast(
                        Callable[[list[TaskImageAttachment]], None],
                        setter_candidate,
                    )

                async def cancel_handler() -> None:
                    await agent.cancel()

                self._abort_handlers[task_id] = cancel_handler
                self._register_abort_handler(
                    manager,
                    device_id,
                    cancel_handler,
                    context=context,
                )
                abort_registered = True

                # Early cancel: if cancel was requested before streaming
                # started (race with cancel_task), skip the stream entirely
                if task_id in self._cancel_requested:
                    final_message = "Task cancelled by user"
                    final_status = TaskStatus.CANCELLED.value
                    stop_reason = "user_stopped"
                elif user_image_attachments and image_attachment_setter is None:
                    final_message = (
                        "Current agent does not support user image attachments"
                    )
                    final_status = TaskStatus.FAILED.value
                    stop_reason = "unsupported_image_attachments"
                else:
                    if user_image_attachments and image_attachment_setter is not None:
                        image_attachment_setter(user_image_attachments)
                    event_type = ""
                    event_data: dict[str, Any] = {}
                    async for event in agent.stream(task["input_text"]):
                        event_type = event["type"]
                        event_data = dict(event.get("data", {}))

                        if event_type == "step":
                            step_count = max(step_count, int(event_data.get("step", 0)))
                            timings = trace_module.get_step_timing_summary(
                                step_count,
                                trace_id=trace_id,
                            )
                            if timings is not None:
                                event_data = {**event_data, "timings": timings}

                        await self._append_task_event(
                            task_id=task_id,
                            event_type=event_type,
                            payload=event_data,
                            role="assistant",
                            trace_id=trace_id,
                            replay_source="classic_chat",
                            task=task,
                        )

                    if event_type == "done":
                        final_message = str(event_data.get("message", ""))
                        final_status = (
                            TaskStatus.SUCCEEDED.value
                            if event_data.get("success", False)
                            else TaskStatus.FAILED.value
                        )
                        stop_reason = str(
                            event_data.get(
                                "stop_reason",
                                "completed"
                                if event_data.get("success", False)
                                else "error",
                            )
                        )
                        step_count = int(event_data.get("steps", step_count))
                    elif event_type == "error":
                        final_message = str(event_data.get("message", "Task failed"))
                        final_status = TaskStatus.FAILED.value
                        stop_reason = str(event_data.get("stop_reason", "error"))
                    elif event_type == "cancelled":
                        final_message = str(
                            event_data.get("message", "Task cancelled by user")
                        )
                        final_status = TaskStatus.CANCELLED.value
                        stop_reason = str(event_data.get("stop_reason", "user_stopped"))

            if not final_message:
                final_message = "Task finished without a final response"
                final_status = TaskStatus.FAILED.value
                stop_reason = "error"

            # If cancel was requested but the stream exited normally (agent
            # sets _is_running=False without raising CancelledError), override
            # the status so the task is recorded as CANCELLED.
            if (
                task_id in self._cancel_requested
                and final_status != TaskStatus.CANCELLED.value
            ):
                final_message = "Task cancelled by user"
                final_status = TaskStatus.CANCELLED.value
                stop_reason = "user_stopped"
        except asyncio.CancelledError:
            if task_id in self._cancel_requested:
                final_message = "Task cancelled by user"
                final_status = TaskStatus.CANCELLED.value
                stop_reason = "user_stopped"
                await self._finalize_traced_task(
                    task_id=task_id,
                    trace_id=trace_id,
                    status=final_status,
                    final_message=final_message,
                    stop_reason=stop_reason,
                    step_count=step_count,
                    metrics_source="chat",
                    start_perf=start_perf,
                )
                return
            raise
        except DeviceBusyError:
            final_message = f"Device {device_id} is busy. Please wait."
            final_status = TaskStatus.FAILED.value
            stop_reason = "device_busy"
        except AgentInitializationError as exc:
            final_message = (
                f"初始化失败: {exc}. 请检查全局配置 (base_url, api_key, model_name)"
            )
            final_status = TaskStatus.FAILED.value
            stop_reason = "initialization_failed"
        except Exception as exc:
            final_message = str(exc)
            final_status = TaskStatus.FAILED.value
            stop_reason = "error"
        finally:
            self._cancel_requested.discard(task_id)
            self._abort_handlers.pop(task_id, None)
            if abort_registered:
                self._unregister_abort_handler(
                    manager,
                    device_id,
                    context=context,
                )
            if final_status == TaskStatus.FAILED.value:
                manager.set_error_state(device_id, final_message, context=context)
            if acquired:
                manager.release_device(device_id, context=context)

        await self._finalize_traced_task(
            task_id=task_id,
            trace_id=trace_id,
            status=final_status,
            final_message=final_message,
            stop_reason=stop_reason,
            step_count=step_count,
            metrics_source="chat",
            start_perf=start_perf,
        )

    async def _execute_layered_chat(self, task: TaskRecord) -> None:
        await self._execute_layered_task(
            task,
            session_id=str(task["session_id"] or task["id"]),
            clear_session_after_run=False,
            metrics_source="layered",
        )

    async def _execute_layered_task(
        self,
        task: TaskRecord,
        *,
        session_id: str,
        clear_session_after_run: bool,
        metrics_source: str,
    ) -> None:
        from AutoGLM_GUI.layered_agent_service import (
            reset_session as reset_layered_session,
            start_run,
        )

        task_id = str(task["id"])
        trace_id = trace_module.create_trace_id()
        start_perf = time.perf_counter()
        final_status = TaskStatus.FAILED.value
        final_message = ""
        stop_reason = "error"
        step_count = 0
        run = None

        try:
            with trace_module.trace_context(trace_id):
                await asyncio.to_thread(self.store.set_task_trace_id, task_id, trace_id)
                await self._write_replay_task_start(
                    task=task,
                    trace_id=trace_id,
                    source=metrics_source,
                )
                run = start_run(
                    task_id=task_id,
                    session_id=session_id,
                    message=str(task["input_text"]),
                )
                self._abort_handlers[task_id] = run.cancel

                async for event in run.stream_events():
                    event_type = str(event["type"])
                    event_payload = dict(event.get("payload", {}))
                    await self._append_task_event(
                        task_id=task_id,
                        event_type=event_type,
                        payload=event_payload,
                        role="assistant",
                        trace_id=trace_id,
                        replay_source=metrics_source,
                        task=task,
                    )

                    if event_type == "tool_result":
                        sub_steps = event_payload.get("steps", 0)
                        if isinstance(sub_steps, (int, float)):
                            step_count += int(sub_steps)
                    elif event_type == "done":
                        final_message = str(event_payload.get("content", ""))
                        final_status = (
                            TaskStatus.SUCCEEDED.value
                            if event_payload.get("success", False)
                            else TaskStatus.FAILED.value
                        )
                        stop_reason = str(
                            event_payload.get(
                                "stop_reason",
                                "completed"
                                if event_payload.get("success", False)
                                else "error",
                            )
                        )
                    elif event_type == "error":
                        final_message = str(event_payload.get("message", "Task failed"))
                        final_status = TaskStatus.FAILED.value
                        stop_reason = str(event_payload.get("stop_reason", "error"))
                    elif event_type == "cancelled":
                        final_message = str(
                            event_payload.get("message", "Task cancelled by user")
                        )
                        final_status = TaskStatus.CANCELLED.value
                        stop_reason = str(
                            event_payload.get("stop_reason", "user_stopped")
                        )

            if not final_message:
                final_message = run.final_output
            if not final_message:
                final_message = "Task finished without a final response"
                final_status = TaskStatus.FAILED.value
                stop_reason = "error"
        except Exception as exc:
            if task_id in self._cancel_requested:
                final_message = "Task cancelled by user"
                final_status = TaskStatus.CANCELLED.value
                stop_reason = "user_stopped"
            else:
                final_message = str(exc)
                final_status = TaskStatus.FAILED.value
                stop_reason = "error"
        finally:
            self._cancel_requested.discard(task_id)
            self._abort_handlers.pop(task_id, None)
            if clear_session_after_run:
                reset_layered_session(session_id)

        await self._finalize_traced_task(
            task_id=task_id,
            trace_id=trace_id,
            status=final_status,
            final_message=final_message,
            stop_reason=stop_reason,
            step_count=step_count,
            metrics_source=metrics_source,
            start_perf=start_perf,
        )

    async def _execute_scheduled_layered_workflow(self, task: TaskRecord) -> None:
        await self._execute_layered_task(
            task,
            session_id=str(task["id"]),
            clear_session_after_run=True,
            metrics_source="scheduled",
        )

    async def _execute_scheduled_workflow(self, task: TaskRecord) -> None:
        from AutoGLM_GUI.exceptions import AgentInitializationError, DeviceBusyError
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

        manager = PhoneAgentManager.get_instance()
        task_id = str(task["id"])
        device_id = str(task["device_id"])
        context = "scheduled"
        trace_id = trace_module.create_trace_id()
        start_perf = time.perf_counter()
        acquired = False
        final_status = TaskStatus.FAILED.value
        final_message = ""
        stop_reason = "error"
        step_count = 0
        abort_registered = False

        try:
            with trace_module.trace_context(trace_id):
                await asyncio.to_thread(self.store.set_task_trace_id, task_id, trace_id)
                await self._write_replay_task_start(
                    task=task,
                    trace_id=trace_id,
                    source="scheduled",
                )
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
                    await agent.cancel()

                self._abort_handlers[task_id] = cancel_handler
                self._register_abort_handler(
                    manager,
                    device_id,
                    cancel_handler,
                    context=context,
                )
                abort_registered = True
                agent.reset()

                # Early cancel: if cancel was requested before streaming started
                if task_id in self._cancel_requested:
                    final_message = "Task cancelled by user"
                    final_status = TaskStatus.CANCELLED.value
                    stop_reason = "user_stopped"
                else:
                    async for event in agent.stream(task["input_text"]):
                        event_type = event["type"]
                        event_data = dict(event.get("data", {}))
                        if event_type == "thinking":
                            await self._append_task_event(
                                task_id=task_id,
                                event_type="thinking",
                                payload=event_data,
                                role="assistant",
                                trace_id=trace_id,
                                replay_source="scheduled",
                                task=task,
                            )
                        elif event_type == "step":
                            step_count = max(
                                step_count,
                                int(event_data.get("step", 0)),
                            )
                            timings = trace_module.get_step_timing_summary(
                                step_count,
                                trace_id=trace_id,
                            )
                            if timings is not None:
                                event_data = {**event_data, "timings": timings}
                            await self._append_task_event(
                                task_id=task_id,
                                event_type="step",
                                payload=event_data,
                                role="assistant",
                                trace_id=trace_id,
                                replay_source="scheduled",
                                task=task,
                            )
                        elif event_type == "done":
                            final_message = str(
                                event_data.get("message", "Task completed")
                            )
                            final_status = (
                                TaskStatus.SUCCEEDED.value
                                if event_data.get("success", False)
                                else TaskStatus.FAILED.value
                            )
                            stop_reason = str(
                                event_data.get(
                                    "stop_reason",
                                    "completed"
                                    if event_data.get("success", False)
                                    else "error",
                                )
                            )
                            step_count = int(event_data.get("steps", step_count))
                        elif event_type == "error":
                            final_message = str(
                                event_data.get("message", "Task failed")
                            )
                            final_status = TaskStatus.FAILED.value
                            stop_reason = str(event_data.get("stop_reason", "error"))
                            await self._append_task_event(
                                task_id=task_id,
                                event_type="error",
                                payload={
                                    "message": final_message,
                                    "stop_reason": stop_reason,
                                },
                                role="assistant",
                                trace_id=trace_id,
                                replay_source="scheduled",
                                task=task,
                            )
                        elif event_type == "cancelled":
                            final_message = str(
                                event_data.get("message", "Task cancelled by user")
                            )
                            final_status = TaskStatus.CANCELLED.value
                            stop_reason = str(
                                event_data.get("stop_reason", "user_stopped")
                            )

                if not final_message:
                    final_message = "Task finished without a final response"
                    final_status = TaskStatus.FAILED.value
                    stop_reason = "error"

                # If cancel was requested but the stream exited normally,
                # override status to CANCELLED.
                if (
                    task_id in self._cancel_requested
                    and final_status != TaskStatus.CANCELLED.value
                ):
                    final_message = "Task cancelled by user"
                    final_status = TaskStatus.CANCELLED.value
                    stop_reason = "user_stopped"
        except asyncio.CancelledError:
            if task_id in self._cancel_requested:
                final_message = "Task cancelled by user"
                final_status = TaskStatus.CANCELLED.value
                stop_reason = "user_stopped"
            else:
                raise
        except DeviceBusyError:
            final_message = f"Device {device_id} is busy. Please wait."
            final_status = TaskStatus.FAILED.value
            stop_reason = "device_busy"
        except AgentInitializationError as exc:
            final_message = (
                f"初始化失败: {exc}. 请检查全局配置 (base_url, api_key, model_name)"
            )
            final_status = TaskStatus.FAILED.value
            stop_reason = "initialization_failed"
        except Exception as exc:
            final_message = str(exc)
            final_status = TaskStatus.FAILED.value
            stop_reason = "error"
        finally:
            self._cancel_requested.discard(task_id)
            self._abort_handlers.pop(task_id, None)
            if abort_registered:
                self._unregister_abort_handler(
                    manager,
                    device_id,
                    context=context,
                )
            if final_status == TaskStatus.FAILED.value:
                manager.set_error_state(device_id, final_message, context=context)
            if acquired:
                manager.release_device(device_id, context=context)

        await self._finalize_traced_task(
            task_id=task_id,
            trace_id=trace_id,
            status=final_status,
            final_message=final_message,
            stop_reason=stop_reason,
            step_count=step_count,
            metrics_source="scheduled",
            start_perf=start_perf,
        )

    async def _finalize_task(
        self,
        *,
        task_id: str,
        status: str,
        final_message: str,
        step_count: int,
        stop_reason: str | None = None,
        trace_id: str | None = None,
        mark_complete: bool = True,
        replay_source: str = "task_finalize",
    ) -> None:
        normalized_stop_reason = stop_reason
        if normalized_stop_reason is None:
            if status == TaskStatus.SUCCEEDED.value:
                normalized_stop_reason = "completed"
            elif status == TaskStatus.CANCELLED.value:
                normalized_stop_reason = "user_stopped"
            else:
                normalized_stop_reason = "error"

        if status == TaskStatus.SUCCEEDED.value:
            event_type = "done"
            payload = {
                "message": final_message,
                "steps": step_count,
                "success": True,
                "stop_reason": normalized_stop_reason,
            }
            error_message = None
        elif status == TaskStatus.CANCELLED.value:
            event_type = "cancelled"
            payload = {
                "message": final_message,
                "stop_reason": normalized_stop_reason,
            }
            error_message = final_message
        else:
            event_type = "error"
            payload = {
                "message": final_message,
                "stop_reason": normalized_stop_reason,
            }
            error_message = final_message

        existing_events = await asyncio.to_thread(self.store.list_task_events, task_id)
        if not any(event["event_type"] == event_type for event in existing_events):
            await self._append_task_event(
                task_id=task_id,
                event_type=event_type,
                payload=payload,
                role="assistant",
                trace_id=trace_id,
                replay_source=replay_source if trace_id else None,
            )

        await asyncio.to_thread(
            self.store.update_task_terminal,
            task_id=task_id,
            status=status,
            final_message=final_message,
            error_message=error_message,
            stop_reason=normalized_stop_reason,
            step_count=step_count,
            trace_id=trace_id,
        )
        if trace_id:
            status_events = await asyncio.to_thread(
                self.store.list_task_events, task_id
            )
            final_status_event = next(
                (
                    event
                    for event in reversed(status_events)
                    if event["event_type"] == "status"
                ),
                None,
            )
            if final_status_event is not None:
                final_task = await asyncio.to_thread(self.store.get_task, task_id)
                await asyncio.to_thread(
                    trace_module.write_replay_event,
                    task_id=task_id,
                    trace_id=trace_id,
                    event_record=final_status_event,
                    source=replay_source,
                    task=final_task,
                )
        if mark_complete:
            self._mark_task_complete(task_id)

    async def _fail_task(self, task: TaskRecord, message: str) -> None:
        await self._append_task_event(
            task_id=task["id"],
            event_type="error",
            payload={"message": message, "stop_reason": "error"},
            role="assistant",
        )
        await self._finalize_task(
            task_id=task["id"],
            status=TaskStatus.FAILED.value,
            final_message=message,
            stop_reason="error",
            step_count=int(task.get("step_count", 0)),
        )

    async def _interrupt_task(self, task: TaskRecord, message: str) -> None:
        await self._append_task_event(
            task_id=task["id"],
            event_type="error",
            payload={"message": message, "stop_reason": "service_interrupted"},
            role="assistant",
        )
        await asyncio.to_thread(
            self.store.update_task_terminal,
            task_id=task["id"],
            status=TaskStatus.INTERRUPTED.value,
            final_message=message,
            error_message=message,
            stop_reason="service_interrupted",
            step_count=int(task.get("step_count", 0)),
        )
        self._mark_task_complete(task["id"])

    def _mark_task_complete(self, task_id: str) -> None:
        event = self._completion_events.setdefault(task_id, asyncio.Event())
        event.set()


task_manager = TaskManager()
