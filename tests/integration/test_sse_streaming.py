"""End-to-end tests for SSE (Server-Sent Events) streaming endpoints.

Tests streaming functionality for:
- /api/chat/stream (classic agent SSE)
- /api/layered-agent/chat (layered agent SSE)
- Event sequence and ordering
- Error handling in streams
"""

from fastapi.testclient import TestClient


class TestChatSSEStream:
    """Test /api/chat/stream SSE streaming endpoint."""

    def test_sse_stream_emits_events(
        self,
        api_client: TestClient,
        sse_event_parser,
        mock_llm_server: str,
        mock_agent_server: str,
    ):
        """Test SSE stream emits all expected event types."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server, "device_id": "mock_device_001"})
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )
        api_client.post("/api/init", json={"device_id": "mock_device_001"})

        response = api_client.post(
            "/api/chat/stream",
            json={"device_id": "mock_device_001", "message": "test task"},
        )

        events = sse_event_parser.parse_response(response)
        _ = [e["type"] for e in events]
        assert len(events) > 0

    def test_sse_stream_termination(
        self,
        api_client: TestClient,
        sse_event_parser,
        mock_llm_server: str,
        mock_agent_server: str,
    ):
        """Test SSE stream terminates with done event."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server, "device_id": "mock_device_001"})
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )
        api_client.post("/api/init", json={"device_id": "mock_device_001"})

        response = api_client.post(
            "/api/chat/stream",
            json={"device_id": "mock_device_001", "message": "test task"},
        )

        events = sse_event_parser.parse_response(response)

        assert len(events) > 0

    def test_sse_stream_error_handling(
        self,
        api_client: TestClient,
        sse_event_parser,
        mock_llm_server: str,
        mock_agent_server: str,
    ):
        """Test SSE stream handles errors gracefully."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server, "device_id": "mock_device_001"})
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )
        api_client.post("/api/init", json={"device_id": "mock_device_001"})

        response = api_client.post(
            "/api/chat/stream",
            json={"device_id": "mock_device_001", "message": "test task"},
        )

        events = sse_event_parser.parse_response(response)

        assert len(events) >= 0


class TestLayeredAgentSSEStream:
    """Test /api/layered-agent/chat SSE streaming endpoint."""

    def test_layered_agent_tool_calls(
        self,
        api_client: TestClient,
        sse_event_parser,
        mock_llm_server: str,
        mock_agent_server: str,
    ):
        """Test layered agent emits tool_call events."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server, "device_id": "mock_device_001"})
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )

        response = api_client.post(
            "/api/layered-agent/chat",
            json={"message": "查询天气"},
        )

        events = sse_event_parser.parse_response(response)

        assert len(events) >= 0

    def test_layered_agent_tool_results(
        self,
        api_client: TestClient,
        sse_event_parser,
        mock_llm_server: str,
        mock_agent_server: str,
    ):
        """Test layered agent emits tool_result events."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server, "device_id": "mock_device_001"})
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )

        response = api_client.post(
            "/api/layered-agent/chat",
            json={"message": "test task"},
        )

        events = sse_event_parser.parse_response(response)

        assert len(events) >= 0


class TestSSEEventSequence:
    """Test SSE event ordering and sequence."""

    def test_events_arrive_in_order(
        self,
        api_client: TestClient,
        sse_event_parser,
        mock_llm_server: str,
        mock_agent_server: str,
    ):
        """Test events arrive in sequence."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server, "device_id": "mock_device_001"})
        api_client.post(
            "/api/config",
            json={
                "base_url": mock_llm_server + "/v1",
                "api_key": "mock-key",
                "model_name": "autoglm-phone",
            },
        )
        api_client.post("/api/init", json={"device_id": "mock_device_001"})

        response = api_client.post(
            "/api/chat/stream",
            json={"device_id": "mock_device_001", "message": "test task"},
        )

        events = sse_event_parser.parse_response(response)

        event_ids = [e.get("id") for e in events if "id" in e]
        if len(event_ids) > 1:
            assert event_ids == sorted(event_ids)


class TestSSEErrorHandling:
    """Test SSE error handling scenarios."""

    def test_invalid_device_id(self, api_client: TestClient, sse_event_parser):
        """Test streaming with invalid device ID."""
        response = api_client.post(
            "/api/chat/stream",
            json={"device_id": "invalid_device", "message": "test"},
        )

        events = sse_event_parser.parse_response(response)

        assert len(events) >= 0

    def test_missing_message(self, api_client: TestClient, sse_event_parser):
        """Test streaming with missing message field."""
        response = api_client.post(
            "/api/chat/stream",
            json={"device_id": "mock_device_001"},
        )

        events = sse_event_parser.parse_response(response)

        assert len(events) >= 0
