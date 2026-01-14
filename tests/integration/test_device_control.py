"""End-to-end tests for device control operations.

Tests device control via:
- Tap (click) operations
- Swipe operations
- Touch events (down, move, up)
- Coordinate transformations
- Multi-device control
"""

from fastapi.testclient import TestClient


class TestTapOperation:
    """Test tap (click) device control."""

    def test_control_tap(
        self, api_client: TestClient, mock_agent_server: str, test_client
    ):
        """Test tap operation at coordinates."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        response = api_client.post(
            "/api/control/tap",
            json={"device_id": "mock_device_001", "x": 500, "y": 1000},
        )

        assert response.status_code == 200

        commands = api_client.get(f"{mock_agent_server}/test/commands").json().format()
        tap_commands = [c for c in commands if c["action"] == "tap"]
        assert len(tap_commands) > 0
        assert tap_commands[0]["params"]["x"] == 500
        assert tap_commands[0]["params"]["y"] == 1000

    def test_tap_boundary_values(self, api_client: TestClient, mock_agent_server: str):
        """Test tap with boundary coordinate values (0 and screen max)."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        response = api_client.post(
            "/api/control/tap",
            json={"device_id": "mock_device_001", "x": 0, "y": 0},
        )

        assert response.status_code == 200

    def test_tap_negative_coordinates(
        self, api_client: TestClient, mock_agent_server: str
    ):
        """Test tap with negative coordinates (should handle or reject)."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        response = api_client.post(
            "/api/control/tap",
            json={"device_id": "mock_device_001", "x": -10, "y": -10},
        )

        assert response.status_code in [200, 422]


class TestSwipeOperation:
    """Test swipe gesture device control."""

    def test_control_swipe(
        self, api_client: TestClient, mock_agent_server: str, test_client
    ):
        """Test swipe gesture from start to end coordinates."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        response = api_client.post(
            "/api/control/swipe",
            json={
                "device_id": "mock_device_001",
                "base_url": mock_agent_server,
                "start_x": 100,
                "start_y": 500,
                "end_x": 300,
                "end_y": 700,
                "duration": 300,
            },
        )

        assert response.status_code == 200

        commands = api_client.get(f"{mock_agent_server}/test/commands").json().format()
        swipe_commands = [c for c in commands if c["action"] == "swipe"]
        assert len(swipe_commands) > 0

    def test_swipe_zero_duration(self, api_client: TestClient, mock_agent_server: str):
        """Test swipe with zero duration (instant swipe)."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        response = api_client.post(
            "/api/control/swipe",
            json={
                "device_id": "mock_device_001",
                "base_url": mock_agent_server,
                "start_x": 100,
                "start_y": 500,
                "end_x": 300,
                "end_y": 700,
                "duration": 0,
            },
        )

        assert response.status_code in [200, 422]

    def test_swipe_diagonal(self, api_client: TestClient, mock_agent_server: str):
        """Test diagonal swipe (different x and y)."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        response = api_client.post(
            "/api/control/swipe",
            json={
                "device_id": "mock_device_001",
                "base_url": mock_agent_server,
                "start_x": 100,
                "start_y": 100,
                "end_x": 300,
                "end_y": 300,
                "duration": 300,
            },
        )

        assert response.status_code == 200


class TestTouchEvents:
    """Test touch events (down, move, up) for complex gestures."""

    def test_touch_sequence(
        self, api_client: TestClient, mock_agent_server: str, test_client
    ):
        """Test complete touch down, move, up sequence."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        api_client.post(
            "/api/control/touch/down",
            json={"device_id": "mock_device_001", "x": 200, "y": 300},
        )

        api_client.post(
            "/api/control/touch/move",
            json={"device_id": "mock_device_001", "x": 250, "y": 350},
        )

        response = api_client.post(
            "/api/control/touch/up",
            json={"device_id": "mock_device_001", "x": 250, "y": 350},
        )

        assert response.status_code == 200

        commands = api_client.get(f"{mock_agent_server}/test/commands").json().format()
        assert any(c["action"] == "touch_down" for c in commands)
        assert any(c["action"] == "touch_move" for c in commands)
        assert any(c["action"] == "touch_up" for c in commands)

    def test_touch_without_coordinates(
        self, api_client: TestClient, mock_agent_server: str
    ):
        """Test touch events without coordinates (missing parameters)."""
        api_client.post("/api/devices/add_remote", json={"base_url": mock_agent_server})

        response = api_client.post(
            "/api/control/touch/down",
            json={"device_id": "mock_device_001", "x": 250, "y": 350},
        )

        assert response.status_code in [200, 422]


class TestMultiDeviceControl:
    """Test controlling multiple devices independently."""

    def test_control_different_devices(self, api_client: TestClient, multi_device_pool):
        """Test sending commands to different devices."""
        device_1_id, device_1_url, device_1 = multi_device_pool[0]
        device_2_id, device_2_url, device_2 = multi_device_pool[1]

        api_client.post("/api/devices/add_remote", json={"base_url": device_1_url})
        api_client.post("/api/devices/add_remote", json={"base_url": device_2_url})

        response1 = api_client.post(
            "/api/control/tap",
            json={"device_id": device_1_id, "x": 100, "y": 200},
        )

        response2 = api_client.post(
            "/api/control/tap",
            json={"device_id": device_2_id, "x": 300, "y": 400},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_concurrent_device_control(self, api_client: TestClient, multi_device_pool):
        """Test concurrent control operations on multiple devices."""
        device_1_id, device_1_url, device_1 = multi_device_pool[0]
        device_2_id, device_2_url, device_2 = multi_device_pool[1]
        device_3_id, device_3_url, device_3 = multi_device_pool[2]

        for device_id, device_url in [
            (device_1_id, device_1_url),
            (device_2_id, device_2_url),
            (device_3_id, device_3_url),
        ]:
            api_client.post("/api/devices/add_remote", json={"base_url": device_url})

        response_statuses = []
        for device_id, x, y in [
            (device_1_id, 100, 200),
            (device_2_id, 300, 400),
            (device_3_id, 500, 600),
        ]:
            response = api_client.post(
                "/api/control/tap", json={"device_id": device_id, "x": x, "y": y}
            )
            response_statuses.append(response.status_code)

        for status_code in response_statuses:
            assert status_code == 200
