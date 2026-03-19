"""Tests for Prometheus metrics endpoint."""

import pytest
from fastapi.testclient import TestClient

from AutoGLM_GUI.api import create_app

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_metrics_endpoint_available(client):
    """Test that /api/metrics endpoint exists."""
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_metrics_contain_required_metrics(client):
    """Test that essential metrics are present."""
    response = client.get("/api/metrics")
    content = response.text

    # Check for key metrics (high priority)
    assert "autoglm_agents_total" in content
    assert "autoglm_agents_busy_count" in content
    assert "autoglm_streaming_sessions_active" in content
    assert "autoglm_agent_last_used_timestamp_seconds" in content
    assert "autoglm_agent_created_timestamp_seconds" in content

    assert "autoglm_devices_total" in content
    assert "autoglm_devices_online_count" in content
    assert "autoglm_device_connections_total" in content
    assert "autoglm_device_unauthorized_connections_total" in content
    assert "autoglm_device_last_seen_timestamp_seconds" in content

    assert "autoglm_build_info" in content


def test_metrics_format_valid(client):
    """Test that metrics follow Prometheus format."""
    response = client.get("/api/metrics")
    content = response.text

    # Should contain TYPE and HELP comments
    assert "# TYPE autoglm_" in content
    assert "# HELP autoglm_" in content

    # Should contain metric values
    assert "autoglm_build_info{" in content


def test_metrics_build_info_values(client):
    """Test that build_info metric has expected labels."""
    response = client.get("/api/metrics")
    content = response.text

    # build_info should have version and python_version labels
    assert 'version="' in content
    assert 'python_version="' in content


def test_metrics_no_errors(client):
    """Test that metrics collection doesn't produce errors."""
    response = client.get("/api/metrics")
    assert response.status_code == 200

    # Metrics should not be empty
    assert len(response.text) > 0

    # Should not contain error indicators
    assert (
        "error" not in response.text.lower() or "error_count" in response.text.lower()
    )


def test_metrics_capture_trace_latency_histograms():
    """Test that trace latency summaries are exported as Prometheus histograms."""
    from AutoGLM_GUI.metrics import (
        get_metrics_registry,
        record_trace_latency_metrics,
        reset_trace_latency_metrics,
    )
    from prometheus_client import generate_latest

    reset_trace_latency_metrics()

    try:
        record_trace_latency_metrics(
            source="chat",
            trace_summary={
                "trace_id": "trace-1",
                "steps": 2,
                "total_duration_ms": 4200.0,
            },
            step_summaries=[
                {
                    "step": 1,
                    "trace_id": "trace-1",
                    "total_duration_ms": 1800.0,
                    "llm_duration_ms": 1200.0,
                    "screenshot_duration_ms": 200.0,
                    "current_app_duration_ms": 50.0,
                    "execute_action_duration_ms": 150.0,
                    "adb_duration_ms": 120.0,
                    "sleep_duration_ms": 80.0,
                },
                {
                    "step": 2,
                    "trace_id": "trace-1",
                    "total_duration_ms": 1600.0,
                    "llm_duration_ms": 900.0,
                    "execute_action_duration_ms": 250.0,
                    "sleep_duration_ms": 100.0,
                },
            ],
        )

        registry = get_metrics_registry()
        output = generate_latest(registry).decode("utf-8")

        assert "autoglm_trace_task_duration_seconds_bucket" in output
        assert 'autoglm_trace_task_duration_seconds_count{source="chat"} 1.0' in output
        assert "autoglm_trace_step_duration_seconds_bucket" in output
        assert 'autoglm_trace_step_duration_seconds_count{source="chat"} 2.0' in output
        assert "autoglm_trace_component_duration_seconds_bucket" in output
        assert 'component="llm"' in output
        assert 'component="sleep"' in output
    finally:
        reset_trace_latency_metrics()


def test_metrics_capture_failed_agents():
    """Test that failed agent initialization is captured in metrics."""
    from AutoGLM_GUI.phone_agent_manager import (
        AgentMetadata,
        AgentState,
        PhoneAgentManager,
    )
    from AutoGLM_GUI.metrics import get_metrics_registry
    from prometheus_client import generate_latest

    manager = PhoneAgentManager.get_instance()

    # Simulate a failed agent initialization (state=ERROR)
    test_device_id = "test_failed_device_123"

    # Directly set state to ERROR in metadata (simulating failed init)
    with manager._manager_lock:
        manager._metadata[test_device_id] = AgentMetadata(
            device_id=test_device_id,
            state=AgentState.ERROR,
            model_config=None,  # type: ignore
            agent_config=None,  # type: ignore
            created_at=0.0,
            last_used=0.0,
            error_message="Test error",
        )

    try:
        # Collect metrics
        registry = get_metrics_registry()
        output = generate_latest(registry).decode("utf-8")

        # Verify that the failed agent appears in metrics
        assert "autoglm_agents_total" in output

        # Verify that state="error" is reported for the test device
        assert 'state="error"' in output

        # Verify that the test device appears with error state
        # (format: autoglm_agents_total{device_id="...",serial="...",state="error"} 1.0)
        lines_with_test_device = [
            line for line in output.split("\n") if test_device_id in line
        ]
        assert len(lines_with_test_device) > 0, "Failed agent not found in metrics"

        # Verify error state is set to 1 for this device
        error_state_line = [
            line
            for line in lines_with_test_device
            if 'state="error"' in line and "1.0" in line
        ]
        assert len(error_state_line) > 0, (
            "Error state not correctly reported for failed agent"
        )

        # Verify timestamps are 0 for failed agent (no metadata)
        timestamp_lines = [
            line
            for line in output.split("\n")
            if test_device_id in line and "timestamp_seconds" in line
        ]
        for line in timestamp_lines:
            if test_device_id in line:
                # Should report 0.0 for failed agents
                assert "0.0" in line, f"Non-zero timestamp for failed agent: {line}"

    finally:
        # Cleanup: remove test state
        with manager._manager_lock:
            manager._metadata.pop(test_device_id, None)
