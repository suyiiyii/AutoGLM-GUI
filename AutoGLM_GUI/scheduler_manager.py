"""Scheduled task manager with APScheduler."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.models.scheduled_task import ScheduledTask


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
        device_serialno: str,
        cron_expression: str,
        enabled: bool = True,
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            workflow_uuid=workflow_uuid,
            device_serialno=device_serialno,
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

    def _execute_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for execution")
            return

        logger.info(f"Executing scheduled task: {task.name}")

        from AutoGLM_GUI.device_manager import DeviceManager
        from AutoGLM_GUI.history_manager import history_manager
        from AutoGLM_GUI.models.history import ConversationRecord, MessageRecord
        from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager
        from AutoGLM_GUI.workflow_manager import workflow_manager

        workflow = workflow_manager.get_workflow(task.workflow_uuid)
        if not workflow:
            self._record_failure(task, "Workflow not found")
            return

        device_manager = DeviceManager.get_instance()
        device = None
        for d in device_manager.get_devices():
            if d.serial == task.device_serialno and d.state.value == "online":
                device = d
                break

        if not device:
            self._record_failure(task, "Device offline")
            return

        manager = PhoneAgentManager.get_instance()
        acquired = manager.acquire_device(
            device.primary_device_id,
            timeout=0,
            raise_on_timeout=False,
            auto_initialize=True,
        )

        if not acquired:
            self._record_failure(task, "Device busy")
            return

        start_time = datetime.now()

        # 收集完整对话消息
        messages: list[MessageRecord] = []
        messages.append(
            MessageRecord(
                role="user",
                content=workflow["text"],
                timestamp=start_time,
            )
        )

        try:
            agent = manager.get_agent(device.primary_device_id)
            agent.reset()

            # 使用 step 循环执行，收集每步信息
            is_first = True
            result_message = ""
            task_success = False

            while agent.step_count < agent.agent_config.max_steps:
                step_result = agent.step(workflow["text"] if is_first else None)
                is_first = False

                # 收集每个 step 的消息
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

            record = ConversationRecord(
                task_text=workflow["text"],
                final_message=result_message,
                success=task_success,
                steps=steps,
                start_time=start_time,
                end_time=end_time,
                duration_ms=int((end_time - start_time).total_seconds() * 1000),
                source="scheduled",
                source_detail=task.name,
                error_message=None if task_success else result_message,
                messages=messages,
            )
            history_manager.add_record(task.device_serialno, record)

            if task_success:
                self._record_success(task, result_message)
            else:
                self._record_failure(task, result_message)

        except Exception as e:
            end_time = datetime.now()
            error_msg = str(e)
            logger.error(f"Scheduled task failed: {task.name} - {error_msg}")

            record = ConversationRecord(
                task_text=workflow["text"],
                final_message=error_msg,
                success=False,
                steps=0,
                start_time=start_time,
                end_time=end_time,
                duration_ms=int((end_time - start_time).total_seconds() * 1000),
                source="scheduled",
                source_detail=task.name,
                error_message=error_msg,
                messages=messages,
            )
            history_manager.add_record(task.device_serialno, record)

            self._record_failure(task, error_msg)

        finally:
            manager.release_device(device.primary_device_id)

    def _record_success(self, task: ScheduledTask, message: str) -> None:
        task.last_run_time = datetime.now()
        task.last_run_success = True
        task.last_run_message = message[:500] if message else ""
        self._save_tasks()
        logger.info(f"Scheduled task completed: {task.name}")

    def _record_failure(self, task: ScheduledTask, error: str) -> None:
        task.last_run_time = datetime.now()
        task.last_run_success = False
        task.last_run_message = error[:500] if error else ""
        self._save_tasks()
        logger.warning(f"Scheduled task failed: {task.name} - {error}")

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
