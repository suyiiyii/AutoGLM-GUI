"""Contract tests for workflow API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.workflow_manager as workflow_manager_module
from AutoGLM_GUI.api.workflows import router as workflows_router

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


class FakeWorkflowManager:
    def __init__(self) -> None:
        self.workflows: dict[str, dict[str, str]] = {}
        self._counter = 0

    def list_workflows(self) -> list[dict[str, str]]:
        return list(self.workflows.values())

    def get_workflow(self, workflow_uuid: str) -> dict[str, str] | None:
        return self.workflows.get(workflow_uuid)

    def create_workflow(self, name: str, text: str) -> dict[str, str]:
        self._counter += 1
        workflow = {
            "uuid": f"wf-{self._counter}",
            "name": name,
            "text": text,
        }
        self.workflows[workflow["uuid"]] = workflow
        return workflow

    def update_workflow(self, uuid: str, name: str, text: str) -> dict[str, str] | None:
        workflow = self.workflows.get(uuid)
        if workflow is None:
            return None
        workflow["name"] = name
        workflow["text"] = text
        return workflow

    def delete_workflow(self, workflow_uuid: str) -> bool:
        if workflow_uuid not in self.workflows:
            return False
        self.workflows.pop(workflow_uuid)
        return True


@pytest.fixture
def fake_manager() -> FakeWorkflowManager:
    return FakeWorkflowManager()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, fake_manager: FakeWorkflowManager
) -> TestClient:
    monkeypatch.setattr(workflow_manager_module, "workflow_manager", fake_manager)

    app = FastAPI()
    app.include_router(workflows_router)
    return TestClient(app)


def test_list_workflows_returns_empty_list(client: TestClient) -> None:
    response = client.get("/api/workflows")

    assert response.status_code == 200
    assert response.json() == {"workflows": []}


def test_create_and_get_workflow(client: TestClient) -> None:
    create_resp = client.post(
        "/api/workflows",
        json={"name": "  Daily Task  ", "text": "  open app  "},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    assert created["uuid"] == "wf-1"
    assert created["name"] == "Daily Task"
    assert created["text"] == "open app"

    get_resp = client.get("/api/workflows/wf-1")
    assert get_resp.status_code == 200
    assert get_resp.json() == created


def test_get_workflow_not_found(client: TestClient) -> None:
    response = client.get("/api/workflows/not-exist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"


def test_update_workflow_success(client: TestClient) -> None:
    client.post("/api/workflows", json={"name": "A", "text": "B"})

    response = client.put(
        "/api/workflows/wf-1",
        json={"name": "Updated", "text": "Run updated workflow"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated"
    assert response.json()["text"] == "Run updated workflow"


def test_update_workflow_not_found(client: TestClient) -> None:
    response = client.put(
        "/api/workflows/not-exist",
        json={"name": "Updated", "text": "Run updated workflow"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow not found"


def test_delete_workflow_success_and_not_found(client: TestClient) -> None:
    client.post("/api/workflows", json={"name": "A", "text": "B"})

    delete_resp = client.delete("/api/workflows/wf-1")
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"success": True, "message": "Workflow deleted"}

    missing_resp = client.delete("/api/workflows/wf-1")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["detail"] == "Workflow not found"


def test_create_workflow_validation_error(client: TestClient) -> None:
    response = client.post("/api/workflows", json={"name": "", "text": "x"})

    assert response.status_code == 422


def test_create_workflow_manager_exception_returns_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_manager: FakeWorkflowManager,
) -> None:
    def broken_create_workflow(name: str, text: str) -> dict[str, str]:
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(fake_manager, "create_workflow", broken_create_workflow)

    response = client.post(
        "/api/workflows",
        json={"name": "X", "text": "Y"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "storage unavailable"
