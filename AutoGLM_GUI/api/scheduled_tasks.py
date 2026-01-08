"""Scheduled tasks API routes."""

from fastapi import APIRouter, HTTPException

from AutoGLM_GUI.scheduler_manager import scheduler_manager
from AutoGLM_GUI.schemas import (
    ScheduledTaskCreate,
    ScheduledTaskListResponse,
    ScheduledTaskResponse,
    ScheduledTaskUpdate,
)

router = APIRouter()


def _task_to_response(task) -> ScheduledTaskResponse:
    next_run = scheduler_manager.get_next_run_time(task.id)
    return ScheduledTaskResponse(
        id=task.id,
        name=task.name,
        workflow_uuid=task.workflow_uuid,
        device_serialno=task.device_serialno,
        cron_expression=task.cron_expression,
        enabled=task.enabled,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        last_run_time=task.last_run_time.isoformat() if task.last_run_time else None,
        last_run_success=task.last_run_success,
        last_run_message=task.last_run_message,
        next_run_time=next_run.isoformat() if next_run else None,
    )


@router.get("/api/scheduled-tasks", response_model=ScheduledTaskListResponse)
def list_scheduled_tasks() -> ScheduledTaskListResponse:
    tasks = scheduler_manager.list_tasks()
    return ScheduledTaskListResponse(tasks=[_task_to_response(t) for t in tasks])


@router.post("/api/scheduled-tasks", response_model=ScheduledTaskResponse)
def create_scheduled_task(request: ScheduledTaskCreate) -> ScheduledTaskResponse:
    from AutoGLM_GUI.workflow_manager import workflow_manager

    workflow = workflow_manager.get_workflow(request.workflow_uuid)
    if not workflow:
        raise HTTPException(status_code=400, detail="Workflow not found")

    task = scheduler_manager.create_task(
        name=request.name,
        workflow_uuid=request.workflow_uuid,
        device_serialno=request.device_serialno,
        cron_expression=request.cron_expression,
        enabled=request.enabled,
    )
    return _task_to_response(task)


@router.get("/api/scheduled-tasks/{task_id}", response_model=ScheduledTaskResponse)
def get_scheduled_task(task_id: str) -> ScheduledTaskResponse:
    task = scheduler_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.put("/api/scheduled-tasks/{task_id}", response_model=ScheduledTaskResponse)
def update_scheduled_task(
    task_id: str, request: ScheduledTaskUpdate
) -> ScheduledTaskResponse:
    update_data = request.model_dump(exclude_unset=True)
    task = scheduler_manager.update_task(task_id, **update_data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.delete("/api/scheduled-tasks/{task_id}")
def delete_scheduled_task(task_id: str) -> dict:
    success = scheduler_manager.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": "Task deleted"}


@router.post("/api/scheduled-tasks/{task_id}/enable")
def enable_scheduled_task(task_id: str) -> dict:
    success = scheduler_manager.set_enabled(task_id, True)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": "Task enabled"}


@router.post("/api/scheduled-tasks/{task_id}/disable")
def disable_scheduled_task(task_id: str) -> dict:
    success = scheduler_manager.set_enabled(task_id, False)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": "Task disabled"}
