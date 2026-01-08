"""定时任务 API 路由."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter()


# Request/Response Models
class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求."""

    name: str
    device_id: str
    message: str
    cron_expression: str
    execution_mode: str = "classic"  # classic, dual_model, layered_agent
    thinking_mode: str = "deep"  # fast, deep, turbo (仅双模型模式有效)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        if len(v) > 100:
            raise ValueError("name too long (max 100 characters)")
        return v.strip()

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message cannot be empty")
        if len(v) > 10000:
            raise ValueError("message too long (max 10000 characters)")
        return v.strip()

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("cron_expression cannot be empty")
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError(
                "cron_expression must have 5 fields: minute hour day month weekday"
            )
        return v.strip()

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, v: str) -> str:
        valid_modes = ["classic", "dual_model", "layered_agent"]
        if v not in valid_modes:
            raise ValueError(f"execution_mode must be one of {valid_modes}")
        return v

    @field_validator("thinking_mode")
    @classmethod
    def validate_thinking_mode(cls, v: str) -> str:
        valid_modes = ["fast", "deep", "turbo"]
        if v not in valid_modes:
            raise ValueError(f"thinking_mode must be one of {valid_modes}")
        return v


class ScheduledTaskUpdate(BaseModel):
    """更新定时任务请求."""

    name: str | None = None
    device_id: str | None = None
    message: str | None = None
    cron_expression: str | None = None
    execution_mode: str | None = None
    thinking_mode: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("name cannot be empty")
        if len(v) > 100:
            raise ValueError("name too long (max 100 characters)")
        return v.strip()

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("message cannot be empty")
        if len(v) > 10000:
            raise ValueError("message too long (max 10000 characters)")
        return v.strip()

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is None:
            return None
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError(
                "cron_expression must have 5 fields: minute hour day month weekday"
            )
        return v.strip()

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_modes = ["classic", "dual_model", "layered_agent"]
        if v not in valid_modes:
            raise ValueError(f"execution_mode must be one of {valid_modes}")
        return v

    @field_validator("thinking_mode")
    @classmethod
    def validate_thinking_mode(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_modes = ["fast", "deep", "turbo"]
        if v not in valid_modes:
            raise ValueError(f"thinking_mode must be one of {valid_modes}")
        return v


class ScheduledTaskResponse(BaseModel):
    """定时任务响应."""

    uuid: str
    name: str
    device_id: str
    message: str
    cron_expression: str
    execution_mode: str = "classic"
    thinking_mode: str = "deep"
    status: str
    created_at: str
    last_run: str | None
    next_run: str | None


class ScheduledTaskListResponse(BaseModel):
    """定时任务列表响应."""

    tasks: list[ScheduledTaskResponse]


class TaskHistoryResponse(BaseModel):
    """执行历史响应."""

    uuid: str
    task_uuid: str
    task_name: str
    device_id: str
    message: str
    execution_mode: str = "classic"
    started_at: str
    finished_at: str | None
    status: str
    result: str | None
    error: str | None


class TaskHistoryListResponse(BaseModel):
    """执行历史列表响应."""

    history: list[TaskHistoryResponse]


# API Routes
@router.get("/api/scheduled-tasks", response_model=ScheduledTaskListResponse)
def list_scheduled_tasks() -> ScheduledTaskListResponse:
    """获取所有定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    tasks = scheduled_task_manager.list_tasks()
    return ScheduledTaskListResponse(tasks=[ScheduledTaskResponse(**t) for t in tasks])


@router.get("/api/scheduled-tasks/{task_uuid}", response_model=ScheduledTaskResponse)
def get_scheduled_task(task_uuid: str) -> ScheduledTaskResponse:
    """获取单个定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    task = scheduled_task_manager.get_task(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return ScheduledTaskResponse(**task)


@router.post("/api/scheduled-tasks", response_model=ScheduledTaskResponse)
def create_scheduled_task(request: ScheduledTaskCreate) -> ScheduledTaskResponse:
    """创建定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    try:
        task = scheduled_task_manager.create_task(
            name=request.name,
            device_id=request.device_id,
            message=request.message,
            cron_expression=request.cron_expression,
            execution_mode=request.execution_mode,
            thinking_mode=request.thinking_mode,
            enabled=request.enabled,
        )
        return ScheduledTaskResponse(**task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/scheduled-tasks/{task_uuid}", response_model=ScheduledTaskResponse)
def update_scheduled_task(
    task_uuid: str, request: ScheduledTaskUpdate
) -> ScheduledTaskResponse:
    """更新定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    try:
        task = scheduled_task_manager.update_task(
            uuid=task_uuid,
            name=request.name,
            device_id=request.device_id,
            message=request.message,
            cron_expression=request.cron_expression,
            execution_mode=request.execution_mode,
            thinking_mode=request.thinking_mode,
        )
        if not task:
            raise HTTPException(status_code=404, detail="Scheduled task not found")
        return ScheduledTaskResponse(**task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/scheduled-tasks/{task_uuid}")
def delete_scheduled_task(task_uuid: str) -> dict:
    """删除定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    success = scheduled_task_manager.delete_task(task_uuid)
    if not success:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return {"success": True, "message": "Scheduled task deleted"}


@router.post("/api/scheduled-tasks/{task_uuid}/enable")
def enable_scheduled_task(task_uuid: str) -> ScheduledTaskResponse:
    """启用定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    task = scheduled_task_manager.enable_task(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return ScheduledTaskResponse(**task)


@router.post("/api/scheduled-tasks/{task_uuid}/disable")
def disable_scheduled_task(task_uuid: str) -> ScheduledTaskResponse:
    """禁用定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    task = scheduled_task_manager.disable_task(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return ScheduledTaskResponse(**task)


@router.post("/api/scheduled-tasks/{task_uuid}/run")
def run_scheduled_task_now(task_uuid: str) -> dict:
    """立即执行定时任务."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    task = scheduled_task_manager.get_task(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    if scheduled_task_manager.is_task_running(task_uuid):
        raise HTTPException(status_code=409, detail="Task is already running")

    success = scheduled_task_manager.run_task_now(task_uuid)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start task")

    return {"success": True, "message": "Task started"}


@router.get("/api/scheduled-tasks/{task_uuid}/history")
def get_task_history(task_uuid: str, limit: int = 50) -> TaskHistoryListResponse:
    """获取任务执行历史."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    # 验证任务存在
    task = scheduled_task_manager.get_task(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    history = scheduled_task_manager.get_task_history(task_uuid, limit)
    return TaskHistoryListResponse(history=[TaskHistoryResponse(**h) for h in history])


@router.get("/api/task-history", response_model=TaskHistoryListResponse)
def get_all_task_history(limit: int = 50) -> TaskHistoryListResponse:
    """获取所有任务的执行历史."""
    from AutoGLM_GUI.scheduled_task_manager import scheduled_task_manager

    history = scheduled_task_manager.get_task_history(limit=limit)
    return TaskHistoryListResponse(history=[TaskHistoryResponse(**h) for h in history])
