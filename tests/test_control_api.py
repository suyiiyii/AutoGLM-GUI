"""Contract tests for low-level control API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.adb_plus as adb_plus
import AutoGLM_GUI.api.control as control_api

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


@pytest.fixture
def control_env(monkeypatch: pytest.MonkeyPatch) -> dict:
    device_calls: list[dict] = []
    touch_calls: dict[str, list[dict]] = {"down": [], "move": [], "up": []}
    should_fail = {
        "tap": False,
        "swipe": False,
        "down": False,
        "move": False,
        "up": False,
    }

    class FakeADBDevice:
        def __init__(self, device_id: str) -> None:
            self.device_id = device_id

        def tap(self, x: int, y: int, delay: float = 0.0) -> None:
            if should_fail["tap"]:
                raise RuntimeError("tap failed")
            device_calls.append(
                {
                    "method": "tap",
                    "device_id": self.device_id,
                    "x": x,
                    "y": y,
                    "delay": delay,
                }
            )

        def swipe(
            self,
            start_x: int,
            start_y: int,
            end_x: int,
            end_y: int,
            duration_ms: int | None = None,
            delay: float = 0.0,
        ) -> None:
            if should_fail["swipe"]:
                raise RuntimeError("swipe failed")
            device_calls.append(
                {
                    "method": "swipe",
                    "device_id": self.device_id,
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "duration_ms": duration_ms,
                    "delay": delay,
                }
            )

    def fake_touch_down(
        x: int, y: int, device_id: str | None = None, delay: float = 0.0
    ) -> None:
        if should_fail["down"]:
            raise RuntimeError("touch_down failed")
        touch_calls["down"].append(
            {"x": x, "y": y, "device_id": device_id, "delay": delay}
        )

    def fake_touch_move(
        x: int, y: int, device_id: str | None = None, delay: float = 0.0
    ) -> None:
        if should_fail["move"]:
            raise RuntimeError("touch_move failed")
        touch_calls["move"].append(
            {"x": x, "y": y, "device_id": device_id, "delay": delay}
        )

    def fake_touch_up(
        x: int, y: int, device_id: str | None = None, delay: float = 0.0
    ) -> None:
        if should_fail["up"]:
            raise RuntimeError("touch_up failed")
        touch_calls["up"].append(
            {"x": x, "y": y, "device_id": device_id, "delay": delay}
        )

    monkeypatch.setattr(control_api, "ADBDevice", FakeADBDevice)
    monkeypatch.setattr(adb_plus, "touch_down", fake_touch_down)
    monkeypatch.setattr(adb_plus, "touch_move", fake_touch_move)
    monkeypatch.setattr(adb_plus, "touch_up", fake_touch_up)

    app = FastAPI()
    app.include_router(control_api.router)

    return {
        "client": TestClient(app),
        "device_calls": device_calls,
        "touch_calls": touch_calls,
        "should_fail": should_fail,
    }


def test_control_tap_requires_device_id(control_env: dict) -> None:
    response = control_env["client"].post(
        "/api/control/tap",
        json={"x": 100, "y": 200},
    )

    assert response.status_code == 200
    assert response.json() == {"success": False, "error": "device_id is required"}


def test_control_tap_success(control_env: dict) -> None:
    response = control_env["client"].post(
        "/api/control/tap",
        json={"x": 100, "y": 200, "device_id": "device-1", "delay": 0.2},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "error": None}
    assert control_env["device_calls"] == [
        {
            "method": "tap",
            "device_id": "device-1",
            "x": 100,
            "y": 200,
            "delay": 0.2,
        }
    ]


def test_control_tap_propagates_runtime_error(control_env: dict) -> None:
    control_env["should_fail"]["tap"] = True

    response = control_env["client"].post(
        "/api/control/tap",
        json={"x": 100, "y": 200, "device_id": "device-1"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"] == "tap failed"


def test_control_swipe_requires_device_id(control_env: dict) -> None:
    response = control_env["client"].post(
        "/api/control/swipe",
        json={"start_x": 1, "start_y": 2, "end_x": 3, "end_y": 4},
    )

    assert response.status_code == 200
    assert response.json() == {"success": False, "error": "device_id is required"}


def test_control_swipe_success(control_env: dict) -> None:
    response = control_env["client"].post(
        "/api/control/swipe",
        json={
            "start_x": 1,
            "start_y": 2,
            "end_x": 3,
            "end_y": 4,
            "duration_ms": 500,
            "device_id": "device-2",
            "delay": 0.1,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "error": None}
    assert control_env["device_calls"][0]["method"] == "swipe"
    assert control_env["device_calls"][0]["duration_ms"] == 500


def test_touch_down_move_up_success(control_env: dict) -> None:
    client = control_env["client"]

    down_resp = client.post(
        "/api/control/touch/down",
        json={"x": 10, "y": 11, "device_id": "device-3", "delay": 0.1},
    )
    move_resp = client.post(
        "/api/control/touch/move",
        json={"x": 12, "y": 13, "device_id": "device-3"},
    )
    up_resp = client.post(
        "/api/control/touch/up",
        json={"x": 14, "y": 15, "device_id": "device-3"},
    )

    assert down_resp.json()["success"] is True
    assert move_resp.json()["success"] is True
    assert up_resp.json()["success"] is True

    assert control_env["touch_calls"]["down"] == [
        {"x": 10, "y": 11, "device_id": "device-3", "delay": 0.1}
    ]
    assert control_env["touch_calls"]["move"] == [
        {"x": 12, "y": 13, "device_id": "device-3", "delay": 0.0}
    ]
    assert control_env["touch_calls"]["up"] == [
        {"x": 14, "y": 15, "device_id": "device-3", "delay": 0.0}
    ]


def test_touch_up_propagates_runtime_error(control_env: dict) -> None:
    control_env["should_fail"]["up"] = True

    response = control_env["client"].post(
        "/api/control/touch/up",
        json={"x": 10, "y": 11, "device_id": "device-3"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"] == "touch_up failed"


def test_control_request_validation_is_enforced(control_env: dict) -> None:
    response = control_env["client"].post(
        "/api/control/tap",
        json={"x": -1, "y": 100, "device_id": "device-1"},
    )

    assert response.status_code == 422
