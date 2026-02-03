"""Scheduled task manager with APScheduler."""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.models.scheduled_task import ScheduledTask

if TYPE_CHECKING:
    from AutoGLM_GUI.models.history import MessageRecord


@dataclass
class DeviceExecutionResult:
    serialno: str
    success: bool
    message: str
    device_model: str = ""


class SchedulerManager:
    _instance: Optional["SchedulerManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._tasks_path = Path.home() / ".config" / "autoglm" / "scheduled_tasks.json"
        self._scheduler = BackgroundScheduler()
        self._tasks: dict[str, ScheduledTask] = {}
        self._file_mtime: Optional[float] = None

    def start(self) -> None:
        self._load_tasks()
        for task in self._tasks.values():
            if task.enabled:
                self._add_job(task)
        self._scheduler.start()
        logger.info(f"SchedulerManager started with {len(self._tasks)} task(s)")

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("SchedulerManager shutdown")

    def create_task(
        self,
        name: str,
        workflow_uuid: str,
        device_serialnos: list[str],
        cron_expression: str,
        enabled: bool = True,
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            workflow_uuid=workflow_uuid,
            device_serialnos=device_serialnos,
            cron_expression=cron_expression,
            enabled=enabled,
        )
        self._tasks[task.id] = task
        self._save_tasks()

        if enabled:
            self._add_job(task)

        logger.info(f"Created scheduled task: {name} (id={task.id})")
        return task

    def update_task(self, task_id: str, **kwargs) -> Optional[ScheduledTask]:
        task = self._tasks.get(task_id)
        if not task:
            return None

        old_enabled = task.enabled
        old_cron = task.cron_expression

        for key, value in kwargs.items():
            if value is not None and hasattr(task, key):
                setattr(task, key, value)

        task.updated_at = datetime.now()
        self._save_tasks()

        if old_enabled and not task.enabled:
            self._remove_job(task_id)
        elif not old_enabled and task.enabled:
            self._add_job(task)
        elif task.enabled and old_cron != task.cron_expression:
            self._remove_job(task_id)
            self._add_job(task)

        logger.info(f"Updated scheduled task: {task.name} (id={task_id})")
        return task

    def delete_task(self, task_id: str) -> bool:
        task = self._tasks.pop(task_id, None)
        if not task:
            return False

        self._remove_job(task_id)
        self._save_tasks()
        logger.info(f"Deleted scheduled task: {task.name} (id={task_id})")
        return True

    def list_tasks(self) -> list[ScheduledTask]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def set_enabled(self, task_id: str, enabled: bool) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.enabled == enabled:
            return True

        task.enabled = enabled
        task.updated_at = datetime.now()
        self._save_tasks()

        if enabled:
            self._add_job(task)
        else:
            self._remove_job(task_id)

        logger.info(f"{'Enabled' if enabled else 'Disabled'} task: {task.name}")
        return True

    def get_next_run_time(self, task_id: str) -> Optional[datetime]:
        job = self._scheduler.get_job(task_id)
        if job and job.next_run_time:
            return job.next_run_time.replace(tzinfo=None)
        return None

    def _add_job(self, task: ScheduledTask) -> None:
        try:
            parts = task.cron_expression.split()
            if len(parts) != 5:
                logger.error(f"Invalid cron expression: {task.cron_expression}")
                return

            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )

            self._scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=task.id,
                args=[task.id],
                replace_existing=True,
            )
            logger.debug(f"Added job for task: {task.name}")
        except Exception as e:
            logger.error(f"Failed to add job for task {task.name}: {e}")

    def _remove_job(self, task_id: str) -> None:
        try:
            if self._scheduler.get_job(task_id):
                self._scheduler.remove_job(task_id)
                logger.debug(f"Removed job: {task_id}")
        except Exception as e:
            logger.warning(f"Failed to remove job {task_id}: {e}")

    def _execute_single_device(
        self,
        serialno: str,
        workflow: dict[str, Any],
        task_name: str,
        manager: Any,
        device_manager: Any,
        history_manager: Any,
    ) -> DeviceExecutionResult:
        from AutoGLM_GUI.models.history import ConversationRecord, MessageRecord

        device = None
        for d in device_manager.get_devices():
            if d.serial == serialno and d.state.value == "online":
                device = d
                break

        if not device:
            return DeviceExecutionResult(
                serialno=serialno,
                success=False,
                message="Device offline",
                device_model="",
            )

        acquired = manager.acquire_device(
            device.primary_device_id,
            timeout=0,
            raise_on_timeout=False,
            auto_initialize=True,
        )

        if not acquired:
            return DeviceExecutionResult(
                serialno=serialno,
                success=False,
                message="Device busy",
                device_model=device.model or serialno,
            )

        start_time = datetime.now()
        messages: list["MessageRecord"] = [
            MessageRecord(
                role="user",
                content=workflow["text"],
                timestamp=start_time,
            )
        ]

        result_message = ""
        task_success = False

        try:
            from AutoGLM_GUI.agents.protocols import is_async_agent

            agent: Any = manager.get_agent(device.primary_device_id)
            agent.reset()

            if is_async_agent(agent):

                async def run_async():
                    nonlocal result_message, task_success
                    stream_gen = agent.stream(workflow["text"])
                    async for event in stream_gen:
                        step_data: dict[str, Any] = event.get("data", {})
                        if event["type"] == "step":
                            messages.append(
                                MessageRecord(
                                    role="assistant",
                                    content="",
                                    timestamp=datetime.now(),
                                    thinking=step_data.get("thinking", ""),
                                    action=step_data.get("action", {}),
                                    step=step_data.get("step", 0),
                                )
                            )
                        elif event["type"] == "done":
                            result_message = step_data.get("message", "Task completed")
                            task_success = step_data.get("success", False)
                            break
                        elif event["type"] == "error":
                            result_message = step_data.get("message", "Task failed")
                            task_success = False
                            break

                asyncio.run(run_async())
            else:
                is_first = True
                while agent.step_count < agent.agent_config.max_steps:
                    step_result = agent.step(workflow["text"] if is_first else None)
                    is_first = False
                    messages.append(
                        MessageRecord(
                            role="assistant",
                            content="",
                            timestamp=datetime.now(),
                            thinking=step_result.thinking,
                            action=step_result.action,
                            step=agent.step_count,
                        )
                    )
                    if step_result.finished:
                        result_message = step_result.message or "Task completed"
                        task_success = step_result.success
                        break
                else:
                    result_message = "Max steps reached"
                    task_success = False

            steps = agent.step_count
            end_time = datetime.now()
            device_model = device.model or serialno

            record = ConversationRecord(
                task_text=workflow["text"],
                final_message=result_message,
                success=task_success,
                steps=steps,
                start_time=start_time,
                end_time=end_time,
                duration_ms=int((end_time - start_time).total_seconds() * 1000),
                source="scheduled",
                source_detail=f"{task_name} [{device_model}]",
                error_message=None if task_success else result_message,
                messages=messages,
            )
            history_manager.add_record(serialno, record)

            return DeviceExecutionResult(
                serialno=serialno,
                success=task_success,
                message=result_message,
                device_model=device_model,
            )

        except Exception as e:
            end_time = datetime.now()
            error_msg = str(e)
            device_model = device.model or serialno

            record = ConversationRecord(
                task_text=workflow["text"],
                final_message=error_msg,
                success=False,
                steps=0,
                start_time=start_time,
                end_time=end_time,
                duration_ms=int((end_time - start_time).total_seconds() * 1000),
                source="scheduled",
                source_detail=f"{task_name} [{device_model}]",
                error_message=error_msg,
                messages=messages,
            )
            history_manager.add_record(serialno, record)

            return DeviceExecutionResult(
                serialno=serialno,
                success=False,
                message=error_msg,
                device_model=device_model,
            )

        finally:
            manager.release_device(device.primary_device_id)

    def _execute_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for execution")
            return

        logger.info(
            f"Executing scheduled task: {task.name} on {len(task.device_serialnos)} device(s)"
        )

        from AutoGLM_GUI.device_manager import DeviceManager
        from AutoGLM_GUI.history_manager import history_manager
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
        from AutoGLM_GUI.workflow_manager import workflow_manager

        workflow = workflow_manager.get_workflow(task.workflow_uuid)
        if not workflow:
            self._record_run(
                task=task,
                status="failure",
                message="Workflow not found",
                success_count=0,
                total_count=len(task.device_serialnos),
            )
            return

        device_manager = DeviceManager.get_instance()
        manager = PhoneAgentManager.get_instance()

        total_count = len(task.device_serialnos)
        if total_count == 0:
            self._record_run(
                task=task,
                status="failure",
                message="No devices selected",
                success_count=0,
                total_count=0,
            )
            return

        results: list[DeviceExecutionResult] = []
        for serialno in task.device_serialnos:
            result = self._execute_single_device(
                serialno=serialno,
                workflow=workflow,
                task_name=task.name,
                manager=manager,
                device_manager=device_manager,
                history_manager=history_manager,
            )
            results.append(result)
            status_icon = "✓" if result.success else "✗"
            logger.info(
                f"  {status_icon} {result.device_model or result.serialno}: {result.message[:50]}"
            )

        success_count = sum(1 for r in results if r.success)
        any_success = success_count > 0
        all_success = success_count == total_count

        summary_parts = []
        for r in results:
            status = "✓" if r.success else "✗"
            short_serial = r.serialno[:8] + "..." if len(r.serialno) > 8 else r.serialno
            display_name = r.device_model or short_serial
            summary_parts.append(f"{status} {display_name}: {r.message[:30]}")
        summary_message = " | ".join(summary_parts)

        logger.info(
            f"Task {task.name} completed: {success_count}/{total_count} devices succeeded"
        )

        status: str
        if all_success:
            status = "success"
        elif any_success:
            status = "partial"
        else:
            status = "failure"

        self._record_run(
            task=task,
            status=status,
            message=summary_message,
            success_count=success_count,
            total_count=total_count,
        )

    def _record_run(
        self,
        task: ScheduledTask,
        status: str,
        message: str,
        success_count: int,
        total_count: int,
    ) -> None:
        task.last_run_time = datetime.now()
        task.last_run_status = status
        task.last_run_success = status == "success"
        task.last_run_success_count = success_count
        task.last_run_total_count = total_count
        task.last_run_message = message[:500] if message else ""
        self._save_tasks()
        if status == "success":
            logger.info(f"Scheduled task completed: {task.name}")
        elif status == "partial":
            logger.warning(f"Scheduled task partially succeeded: {task.name}")
        else:
            logger.warning(f"Scheduled task failed: {task.name} - {message}")

    def _load_tasks(self) -> None:
        if not self._tasks_path.exists():
            return

        try:
            with open(self._tasks_path, encoding="utf-8") as f:
                data = json.load(f)
            tasks_data = data.get("tasks", [])
            self._tasks = {t["id"]: ScheduledTask.from_dict(t) for t in tasks_data}
            self._file_mtime = self._tasks_path.stat().st_mtime
            logger.debug(f"Loaded {len(self._tasks)} scheduled tasks")
        except Exception as e:
            logger.warning(f"Failed to load scheduled tasks: {e}")

    def _save_tasks(self) -> None:
        self._tasks_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._tasks_path.with_suffix(".tmp")

        try:
            data = {"tasks": [t.to_dict() for t in self._tasks.values()]}
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self._tasks_path)
            self._file_mtime = self._tasks_path.stat().st_mtime
            logger.debug(f"Saved {len(self._tasks)} scheduled tasks")
        except Exception as e:
            logger.error(f"Failed to save scheduled tasks: {e}")
            if temp_path.exists():
                temp_path.unlink()


scheduler_manager = SchedulerManager()
