"""End-to-end tests for workflow management.

Tests workflow CRUD operations:
- Create workflow
- List workflows
- Get workflow details
- Update workflow
- Delete workflow
- Execute workflow with agent
"""

from fastapi.testclient import TestClient


class TestWorkflowCRUD:
    """Test workflow create, read, update, delete operations."""

    def test_create_workflow(self, api_client: TestClient):
        """Test creating a new workflow."""
        response = api_client.post(
            "/api/workflows",
            json={
                "name": "测试工作流",
                "text": "点击消息按钮",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "uuid" in data
        assert data["name"] == "测试工作流"
        assert data["text"] == "点击消息按钮"

    def test_create_workflow_empty_name(self, api_client: TestClient):
        """Test creating workflow with empty name."""
        response = api_client.post(
            "/api/workflows",
            json={"name": "", "text": "test task"},
        )

        assert response.status_code in [200, 422]

    def test_list_workflows(self, api_client: TestClient):
        """Test listing all workflows."""
        response = api_client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
        assert isinstance(data["workflows"], list)

    def test_list_workflows_pagination(
        self, api_client: TestClient, mock_llm_server: str, mock_agent_server: str
    ):
        """Test workflow list with pagination parameters."""
        for i in range(5):
            api_client.post(
                "/api/workflows",
                json={
                    "name": f"Workflow {i}",
                    "task": f"Task {i}",
                },
            )

        response = api_client.get("/api/workflows", params={"page": 1, "page_size": 10})

        assert response.status_code == 200

    def test_get_workflow(self, api_client: TestClient):
        """Test getting a single workflow by UUID."""
        create_response = api_client.post(
            "/api/workflows",
            json={"name": "Test Workflow", "text": "Test task"},
        )

        workflow_uuid = create_response.json()["uuid"]

        response = api_client.get(f"/api/workflows/{workflow_uuid}")

        assert response.status_code == 200
        data = response.json()
        assert data["uuid"] == workflow_uuid
        assert data["name"] == "Test Workflow"

    def test_get_nonexistent_workflow(self, api_client: TestClient):
        """Test getting a workflow that doesn't exist."""
        response = api_client.get("/api/workflows/nonexistent-uuid")

        assert response.status_code in [200, 404]

    def test_update_workflow(self, api_client: TestClient):
        """Test updating an existing workflow."""
        create_response = api_client.post(
            "/api/workflows",
            json={"name": "Original Name", "text": "Original task"},
        )

        workflow_uuid = create_response.json()["uuid"]

        response = api_client.put(
            f"/api/workflows/{workflow_uuid}",
            json={"name": "Updated Name", "text": "Updated task"},
        )

        assert response.status_code == 200

        response = api_client.get(f"/api/workflows/{workflow_uuid}")
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["text"] == "Updated task"

    def test_delete_workflow(self, api_client: TestClient):
        """Test deleting a workflow."""
        create_response = api_client.post(
            "/api/workflows",
            json={"name": "To Delete", "text": "Delete me"},
        )

        workflow_uuid = create_response.json()["uuid"]

        response = api_client.delete(f"/api/workflows/{workflow_uuid}")

        assert response.status_code == 200

        response = api_client.get(f"/api/workflows/{workflow_uuid}")
        assert response.status_code in [200, 404]

    def test_delete_nonexistent_workflow(self, api_client: TestClient):
        """Test deleting a workflow that doesn't exist."""
        response = api_client.delete("/api/workflows/nonexistent-uuid")

        assert response.status_code in [200, 404]


class TestWorkflowExecution:
    """Test executing workflows with agent."""

    def test_workflow_task_execution(
        self, api_client: TestClient, mock_llm_server: str, mock_agent_server: str
    ):
        """Test that workflow task is executed correctly."""
        api_client.post("/api/devices/add_remote", json={"url": mock_agent_server})
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )

        workflow_response = api_client.post(
            "/api/workflows",
            json={
                "name": "Execution Test",
                "text": "打开设置应用",
            },
        )

        workflow_task = workflow_response.json()["text"]

        api_client.post("/api/init", json={"device_id": "mock_device_001"})

        response = api_client.post(
            "/api/chat",
            json={"device_id": "mock_device_001", "message": workflow_task},
        )

        assert response.status_code == 200
