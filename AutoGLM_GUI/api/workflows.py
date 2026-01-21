"""Workflow API 路由."""

from fastapi import APIRouter, HTTPException

from AutoGLM_GUI.schemas import (
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowUpdate,
)

router = APIRouter()


@router.get("/api/workflows", response_model=WorkflowListResponse)
def list_workflows() -> WorkflowListResponse:
    """获取所有 workflows."""
    from AutoGLM_GUI.workflow_manager import workflow_manager

    workflow_dicts = workflow_manager.list_workflows()
    workflows = [WorkflowResponse(**wf) for wf in workflow_dicts]
    return WorkflowListResponse(workflows=workflows)


@router.get("/api/workflows/{workflow_uuid}", response_model=WorkflowResponse)
def get_workflow(workflow_uuid: str) -> WorkflowResponse:
    """获取单个 workflow."""
    from AutoGLM_GUI.workflow_manager import workflow_manager

    workflow = workflow_manager.get_workflow(workflow_uuid)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(**workflow)


@router.post("/api/workflows", response_model=WorkflowResponse)
def create_workflow(request: WorkflowCreate) -> WorkflowResponse:
    """创建新 workflow."""
    from AutoGLM_GUI.workflow_manager import workflow_manager

    try:
        workflow = workflow_manager.create_workflow(
            name=request.name, text=request.text
        )
        return WorkflowResponse(**workflow)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/workflows/{workflow_uuid}", response_model=WorkflowResponse)
def update_workflow(workflow_uuid: str, request: WorkflowUpdate) -> WorkflowResponse:
    """更新 workflow."""
    from AutoGLM_GUI.workflow_manager import workflow_manager

    workflow = workflow_manager.update_workflow(
        uuid=workflow_uuid, name=request.name, text=request.text
    )
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(**workflow)


@router.delete("/api/workflows/{workflow_uuid}")
def delete_workflow(workflow_uuid: str) -> dict:
    """删除 workflow."""
    from AutoGLM_GUI.workflow_manager import workflow_manager

    success = workflow_manager.delete_workflow(workflow_uuid)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"success": True, "message": "Workflow deleted"}
