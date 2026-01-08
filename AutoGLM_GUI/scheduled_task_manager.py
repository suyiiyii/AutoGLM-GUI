"""定时任务管理模块.

Features:
- 单例模式
- JSON 文件持久化
- APScheduler 调度器
- Cron 表达式支持
- 任务执行历史记录
- 支持多种执行模式（经典、双模型、分层代理）
"""

import asyncio
import json
import threading
import uuid as uuid_lib
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from AutoGLM_GUI.logger import logger


class TaskStatus(str, Enum):
    """任务状态."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    RUNNING = "running"


class ExecutionStatus(str, Enum):
    """执行状态."""

    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"


class ExecutionMode(str, Enum):
    """执行模式."""

    CLASSIC = "classic"  # 经典模式（单模型）
    DUAL_MODEL = "dual_model"  # 双模型协作
    LAYERED_AGENT = "layered_agent"  # 分层代理


class ScheduledTaskManager:
    """定时任务管理器（单例模式）."""

    _instance: "ScheduledTaskManager | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._tasks_path = Path.home() / ".config" / "autoglm" / "scheduled_tasks.json"
        self._history_path = Path.home() / ".config" / "autoglm" / "task_history.json"
        self._file_cache: list[dict] | None = None
        self._file_mtime: float | None = None
        self._scheduler: AsyncIOScheduler | None = None
        self._task_executor: Callable[[str, str, str, str], None] | None = None
        self._running_tasks: set[str] = set()

    def set_task_executor(
        self, executor: Callable[[str, str, str, str], str]
    ) -> None:
        """设置任务执行器.

        Args:
            executor: 执行函数，参数为 (task_uuid, device_id, message, execution_mode)，返回执行结果字符串
        """
        self._task_executor = executor

    def start_scheduler(self) -> None:
        """启动调度器."""
        if self._scheduler is not None and self._scheduler.running:
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        logger.info("Scheduled task scheduler started")

        # 加载并注册所有启用的任务
        tasks = self._load_tasks()
        for task in tasks:
            if task.get("status") == TaskStatus.ENABLED.value:
                self._register_job(task)

    def stop_scheduler(self) -> None:
        """停止调度器."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("Scheduled task scheduler stopped")

    def list_tasks(self) -> list[dict]:
        """获取所有定时任务."""
        return self._load_tasks()

    def get_task(self, uuid: str) -> dict | None:
        """根据 UUID 获取任务."""
        tasks = self._load_tasks()
        return next((t for t in tasks if t["uuid"] == uuid), None)

    def create_task(
        self,
        name: str,
        device_id: str,
        message: str,
        cron_expression: str,
        execution_mode: str = ExecutionMode.CLASSIC.value,
        thinking_mode: str = "deep",
        enabled: bool = True,
    ) -> dict:
        """创建定时任务.

        Args:
            name: 任务名称
            device_id: 目标设备 ID
            message: 要执行的指令
            cron_expression: Cron 表达式 (分 时 日 月 周)
            execution_mode: 执行模式 (classic/dual_model/layered_agent)
            thinking_mode: 思考模式 (fast/deep/turbo)，仅双模型模式有效
            enabled: 是否启用

        Returns:
            dict: 新创建的任务
        """
        # 验证 cron 表达式
        self._validate_cron(cron_expression)

        # 验证执行模式
        valid_modes = [m.value for m in ExecutionMode]
        if execution_mode not in valid_modes:
            raise ValueError(f"Invalid execution_mode: {execution_mode}")

        tasks = self._load_tasks()
        new_task = {
            "uuid": str(uuid_lib.uuid4()),
            "name": name,
            "device_id": device_id,
            "message": message,
            "cron_expression": cron_expression,
            "execution_mode": execution_mode,
            "thinking_mode": thinking_mode,
            "status": TaskStatus.ENABLED.value
            if enabled
            else TaskStatus.DISABLED.value,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "next_run": None,
        }

        tasks.append(new_task)
        self._save_tasks(tasks)

        # 如果启用，注册到调度器
        if enabled and self._scheduler is not None:
            self._register_job(new_task)
            # 更新 next_run
            new_task["next_run"] = self._get_next_run_time(new_task["uuid"])

        logger.info(
            f"Created scheduled task: {name} (uuid={new_task['uuid']}, mode={execution_mode})"
        )
        return new_task

    def update_task(
        self,
        uuid: str,
        name: str | None = None,
        device_id: str | None = None,
        message: str | None = None,
        cron_expression: str | None = None,
        execution_mode: str | None = None,
        thinking_mode: str | None = None,
    ) -> dict | None:
        """更新任务."""
        tasks = self._load_tasks()
        for task in tasks:
            if task["uuid"] == uuid:
                if name is not None:
                    task["name"] = name
                if device_id is not None:
                    task["device_id"] = device_id
                if message is not None:
                    task["message"] = message
                if cron_expression is not None:
                    self._validate_cron(cron_expression)
                    task["cron_expression"] = cron_expression
                if execution_mode is not None:
                    valid_modes = [m.value for m in ExecutionMode]
                    if execution_mode not in valid_modes:
                        raise ValueError(f"Invalid execution_mode: {execution_mode}")
                    task["execution_mode"] = execution_mode
                if thinking_mode is not None:
                    task["thinking_mode"] = thinking_mode

                self._save_tasks(tasks)

                # 如果任务已启用，重新注册
                if task["status"] == TaskStatus.ENABLED.value:
                    self._unregister_job(uuid)
                    self._register_job(task)
                    task["next_run"] = self._get_next_run_time(uuid)

                logger.info(f"Updated scheduled task: uuid={uuid}")
                return task
        return None

    def delete_task(self, uuid: str) -> bool:
        """删除任务."""
        tasks = self._load_tasks()
        original_len = len(tasks)
        tasks = [t for t in tasks if t["uuid"] != uuid]

        if len(tasks) < original_len:
            self._save_tasks(tasks)
            self._unregister_job(uuid)
            logger.info(f"Deleted scheduled task: uuid={uuid}")
            return True
        return False

    def enable_task(self, uuid: str) -> dict | None:
        """启用任务."""
        tasks = self._load_tasks()
        for task in tasks:
            if task["uuid"] == uuid:
                if task["status"] == TaskStatus.RUNNING.value:
                    return task  # 运行中不改变状态

                task["status"] = TaskStatus.ENABLED.value
                self._save_tasks(tasks)
                self._register_job(task)
                task["next_run"] = self._get_next_run_time(uuid)
                logger.info(f"Enabled scheduled task: uuid={uuid}")
                return task
        return None

    def disable_task(self, uuid: str) -> dict | None:
        """禁用任务."""
        tasks = self._load_tasks()
        for task in tasks:
            if task["uuid"] == uuid:
                if task["status"] == TaskStatus.RUNNING.value:
                    return task  # 运行中不改变状态

                task["status"] = TaskStatus.DISABLED.value
                task["next_run"] = None
                self._save_tasks(tasks)
                self._unregister_job(uuid)
                logger.info(f"Disabled scheduled task: uuid={uuid}")
                return task
        return None

    def run_task_now(self, uuid: str) -> bool:
        """立即执行任务."""
        task = self.get_task(uuid)
        if not task:
            return False

        if uuid in self._running_tasks:
            logger.warning(f"Task {uuid} is already running")
            return False

        # 在后台线程中异步执行
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._execute_task(task))
            finally:
                loop.close()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        return True

    def get_task_history(
        self, task_uuid: str | None = None, limit: int = 50
    ) -> list[dict]:
        """获取执行历史."""
        history = self._load_history()

        if task_uuid:
            history = [h for h in history if h.get("task_uuid") == task_uuid]

        # 按时间倒序，取最近 limit 条
        history.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return history[:limit]

    def is_task_running(self, uuid: str) -> bool:
        """检查任务是否正在运行."""
        return uuid in self._running_tasks

    async def _execute_task(self, task: dict) -> None:
        """执行任务."""
        uuid = task["uuid"]
        if uuid in self._running_tasks:
            return

        self._running_tasks.add(uuid)
        self._update_task_status(uuid, TaskStatus.RUNNING)

        execution_mode = task.get("execution_mode", ExecutionMode.CLASSIC.value)

        execution_record = {
            "uuid": str(uuid_lib.uuid4()),
            "task_uuid": uuid,
            "task_name": task["name"],
            "device_id": task["device_id"],
            "message": task["message"],
            "execution_mode": execution_mode,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "status": ExecutionStatus.FAILED.value,
            "result": None,
            "error": None,
        }

        try:
            if self._task_executor is None:
                raise RuntimeError("Task executor not set")

            # 调用执行器，传入执行模式，并获取详细结果
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._task_executor,
                uuid,
                task["device_id"],
                task["message"],
                execution_mode,
            )

            execution_record["status"] = ExecutionStatus.SUCCESS.value
            execution_record["result"] = result if result else "Task completed"
            logger.info(
                f"Scheduled task executed successfully: {task['name']} (mode={execution_mode})"
            )

        except Exception as e:
            execution_record["status"] = ExecutionStatus.FAILED.value
            execution_record["error"] = str(e)
            logger.error(f"Scheduled task failed: {task['name']}, error: {e}")

        finally:
            execution_record["finished_at"] = datetime.now().isoformat()
            self._save_execution_record(execution_record)

            self._running_tasks.discard(uuid)

            # 恢复原状态
            current_task = self.get_task(uuid)
            if current_task and current_task["status"] == TaskStatus.RUNNING.value:
                self._update_task_status(uuid, TaskStatus.ENABLED)
                self._update_last_run(uuid)

    def _register_job(self, task: dict) -> None:
        """注册调度任务."""
        if self._scheduler is None:
            return

        uuid = task["uuid"]
        cron = task["cron_expression"]

        # 移除已存在的同名任务
        self._unregister_job(uuid)

        try:
            trigger = CronTrigger.from_crontab(cron)
            self._scheduler.add_job(
                self._job_wrapper_sync,
                trigger=trigger,
                id=uuid,
                args=[task],
                replace_existing=True,
            )
            logger.debug(f"Registered job: {uuid} with cron: {cron}")
        except Exception as e:
            logger.error(f"Failed to register job {uuid}: {e}")

    def _unregister_job(self, uuid: str) -> None:
        """取消注册调度任务."""
        if self._scheduler is None:
            return

        try:
            self._scheduler.remove_job(uuid)
            logger.debug(f"Unregistered job: {uuid}")
        except Exception:
            pass  # 任务可能不存在

    def _job_wrapper_sync(self, task: dict) -> None:
        """调度任务同步包装器."""
        current_task = self.get_task(task["uuid"])
        if current_task and current_task["status"] != TaskStatus.DISABLED.value:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._execute_task(current_task))
            finally:
                loop.close()

    def _get_next_run_time(self, uuid: str) -> str | None:
        """获取下次执行时间."""
        if self._scheduler is None:
            return None

        job = self._scheduler.get_job(uuid)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def _update_task_status(self, uuid: str, status: TaskStatus) -> None:
        """更新任务状态."""
        tasks = self._load_tasks()
        for task in tasks:
            if task["uuid"] == uuid:
                task["status"] = status.value
                break
        self._save_tasks(tasks)

    def _update_last_run(self, uuid: str) -> None:
        """更新最后执行时间."""
        tasks = self._load_tasks()
        for task in tasks:
            if task["uuid"] == uuid:
                task["last_run"] = datetime.now().isoformat()
                task["next_run"] = self._get_next_run_time(uuid)
                break
        self._save_tasks(tasks)

    def _validate_cron(self, cron_expression: str) -> None:
        """验证 cron 表达式."""
        try:
            CronTrigger.from_crontab(cron_expression)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {cron_expression}. {e}")

    def _load_tasks(self) -> list[dict]:
        """从文件加载任务."""
        if not self._tasks_path.exists():
            return []

        current_mtime = self._tasks_path.stat().st_mtime
        if self._file_mtime == current_mtime and self._file_cache is not None:
            return self._file_cache.copy()

        try:
            with open(self._tasks_path, encoding="utf-8") as f:
                data = json.load(f)
            tasks = data.get("tasks", [])
            self._file_cache = tasks
            self._file_mtime = current_mtime
            return tasks.copy()
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load scheduled tasks: {e}")
            return []

    def _save_tasks(self, tasks: list[dict]) -> bool:
        """保存任务到文件."""
        self._tasks_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = self._tasks_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump({"tasks": tasks}, f, indent=2, ensure_ascii=False)
            temp_path.replace(self._tasks_path)

            self._file_cache = tasks.copy()
            self._file_mtime = self._tasks_path.stat().st_mtime
            return True
        except Exception as e:
            logger.error(f"Failed to save scheduled tasks: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False

    def _load_history(self) -> list[dict]:
        """加载执行历史."""
        if not self._history_path.exists():
            return []

        try:
            with open(self._history_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("history", [])
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_execution_record(self, record: dict) -> None:
        """保存执行记录."""
        self._history_path.parent.mkdir(parents=True, exist_ok=True)

        history = self._load_history()
        history.append(record)

        # 只保留最近 500 条记录
        if len(history) > 500:
            history = history[-500:]

        try:
            with open(self._history_path, "w", encoding="utf-8") as f:
                json.dump({"history": history}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save execution history: {e}")


# 单例实例
scheduled_task_manager = ScheduledTaskManager()
