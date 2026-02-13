"""Contract tests for media API endpoints."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import AutoGLM_GUI.api.media as media_api
import AutoGLM_GUI.device_manager as device_manager_module
from AutoGLM_GUI.exceptions import DeviceNotAvailableError

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


@dataclass
class FakeConnectionType:
    value: str


@dataclass
class FakeManagedDevice:
    connection_type: FakeConnectionType


@dataclass
class FakeScreenshot:
    base64_data: str
    width: int
    height: int
    is_sensitive: bool


class FakeRemoteDevice:
    def __init__(self, screenshot: FakeScreenshot) -> None:
        self._screenshot = screenshot

    def get_screenshot(self, timeout: int = 10) -> FakeScreenshot:
        return self._screenshot


class FakeDeviceManager:
    def __init__(self) -> None:
        self.device_id_to_serial = {
            "local-device": "serial-local",
            "remote-device": "serial-remote",
        }
        self.serial_to_device = {
            "serial-local": FakeManagedDevice(FakeConnectionType("usb")),
            "serial-remote": FakeManagedDevice(FakeConnectionType("remote")),
        }
        self.remote_instances = {
            "serial-remote": FakeRemoteDevice(
                FakeScreenshot(
                    base64_data="REMOTE_IMG",
                    width=800,
                    height=1600,
                    is_sensitive=True,
                )
            )
        }

    def get_serial_by_device_id(self, device_id: str) -> str | None:
        return self.device_id_to_serial.get(device_id)

    def get_device_by_serial(self, serial: str) -> FakeManagedDevice | None:
        return self.serial_to_device.get(serial)

    def get_remote_device_instance(self, serial: str) -> FakeRemoteDevice | None:
        return self.remote_instances.get(serial)


@pytest.fixture
def media_env(monkeypatch: pytest.MonkeyPatch) -> dict:
    fake_manager = FakeDeviceManager()
    reset_calls: list[str | None] = []
    captured_requests: list[str | None] = []

    class FakeDeviceManagerClass:
        @staticmethod
        def get_instance() -> FakeDeviceManager:
            return fake_manager

    def fake_stop_streamers(device_id: str | None = None) -> None:
        reset_calls.append(device_id)

    def fake_capture_screenshot(device_id: str | None = None) -> FakeScreenshot:
        captured_requests.append(device_id)
        return FakeScreenshot(
            base64_data="LOCAL_IMG",
            width=1080,
            height=1920,
            is_sensitive=False,
        )

    monkeypatch.setattr(device_manager_module, "DeviceManager", FakeDeviceManagerClass)
    monkeypatch.setattr(media_api, "stop_streamers", fake_stop_streamers)
    monkeypatch.setattr(media_api, "capture_screenshot", fake_capture_screenshot)

    app = FastAPI()
    app.include_router(media_api.router)

    return {
        "client": TestClient(app),
        "manager": fake_manager,
        "reset_calls": reset_calls,
        "captured_requests": captured_requests,
    }


def test_reset_video_stream_all(media_env: dict) -> None:
    response = media_env["client"].post("/api/video/reset")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "All video streams reset"}
    assert media_env["reset_calls"] == [None]


def test_reset_video_stream_single_device(media_env: dict) -> None:
    response = media_env["client"].post("/api/video/reset", params={"device_id": "d1"})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Video stream reset for device d1",
    }
    assert media_env["reset_calls"] == ["d1"]


def test_screenshot_requires_device_id(media_env: dict) -> None:
    response = media_env["client"].post("/api/screenshot", json={})

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "image": "",
        "width": 0,
        "height": 0,
        "is_sensitive": False,
        "error": "device_id is required",
    }


def test_screenshot_device_not_found(media_env: dict) -> None:
    response = media_env["client"].post(
        "/api/screenshot",
        json={"device_id": "unknown-device"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"] == "Device unknown-device not found"


def test_screenshot_local_device_success(media_env: dict) -> None:
    response = media_env["client"].post(
        "/api/screenshot",
        json={"device_id": "local-device"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "image": "LOCAL_IMG",
        "width": 1080,
        "height": 1920,
        "is_sensitive": False,
        "error": None,
    }
    assert media_env["captured_requests"] == ["local-device"]


def test_screenshot_remote_device_success(media_env: dict) -> None:
    response = media_env["client"].post(
        "/api/screenshot",
        json={"device_id": "remote-device"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "image": "REMOTE_IMG",
        "width": 800,
        "height": 1600,
        "is_sensitive": True,
        "error": None,
    }


def test_screenshot_remote_device_missing_instance(media_env: dict) -> None:
    media_env["manager"].remote_instances.pop("serial-remote", None)

    response = media_env["client"].post(
        "/api/screenshot",
        json={"device_id": "remote-device"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"] == "Remote device serial-remote not found"


def test_screenshot_handles_device_not_available_error(
    media_env: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unavailable(device_id: str | None = None) -> FakeScreenshot:
        raise DeviceNotAvailableError("device temporarily offline")

    monkeypatch.setattr(media_api, "capture_screenshot", raise_unavailable)

    response = media_env["client"].post(
        "/api/screenshot",
        json={"device_id": "local-device"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"] == "device temporarily offline"
