"""Contract tests for MCP tool implementations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

import AutoGLM_GUI.api.mcp as mcp_api
import AutoGLM_GUI.device_manager as device_manager_module
from AutoGLM_GUI.exceptions import DeviceNotAvailableError

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


@dataclass
class FakeScreenshot:
    base64_data: str
    width: int
    height: int
    is_sensitive: bool


class FakeDevice:
    def __init__(self, screenshot: FakeScreenshot) -> None:
        self._screenshot = screenshot

    def get_screenshot(self, timeout: int = 10) -> FakeScreenshot:
        return self._screenshot


class FakeDeviceManager:
    def __init__(self) -> None:
        self._devices: dict[str, FakeDevice] = {
            "local-device": FakeDevice(
                FakeScreenshot(
                    base64_data="LOCAL_IMG",
                    width=1080,
                    height=1920,
                    is_sensitive=False,
                )
            ),
            "remote-device": FakeDevice(
                FakeScreenshot(
                    base64_data="REMOTE_IMG",
                    width=800,
                    height=1600,
                    is_sensitive=True,
                )
            ),
        }

    def get_device_protocol(self, device_id: str) -> FakeDevice:
        if device_id not in self._devices:
            raise ValueError(f"Device {device_id} not found")
        return self._devices[device_id]


@pytest.fixture
def mcp_env(monkeypatch: pytest.MonkeyPatch) -> dict:
    fake_manager = FakeDeviceManager()

    class FakeDeviceManagerClass:
        @staticmethod
        def get_instance() -> FakeDeviceManager:
            return fake_manager

    monkeypatch.setattr(device_manager_module, "DeviceManager", FakeDeviceManagerClass)

    return {
        "manager": fake_manager,
    }


def test_mcp_screenshot_requires_device_id(mcp_env: dict) -> None:
    result = asyncio.run(mcp_api.screenshot(""))

    assert result.model_dump() == {
        "success": False,
        "image": "",
        "width": 0,
        "height": 0,
        "is_sensitive": False,
        "error": "device_id is required",
    }


def test_mcp_screenshot_device_not_found(mcp_env: dict) -> None:
    result = asyncio.run(mcp_api.screenshot("unknown-device"))

    assert result.success is False
    assert "Device unknown-device not found" in result.error


def test_mcp_screenshot_local_device_success(mcp_env: dict) -> None:
    result = asyncio.run(mcp_api.screenshot("local-device"))

    assert result.model_dump() == {
        "success": True,
        "image": "LOCAL_IMG",
        "width": 1080,
        "height": 1920,
        "is_sensitive": False,
        "error": None,
    }


def test_mcp_screenshot_remote_device_success(mcp_env: dict) -> None:
    result = asyncio.run(mcp_api.screenshot("remote-device"))

    assert result.model_dump() == {
        "success": True,
        "image": "REMOTE_IMG",
        "width": 800,
        "height": 1600,
        "is_sensitive": True,
        "error": None,
    }


def test_mcp_screenshot_remote_device_missing_instance(mcp_env: dict) -> None:
    mcp_env["manager"]._devices.pop("remote-device", None)

    result = asyncio.run(mcp_api.screenshot("remote-device"))

    assert result.success is False
    assert "Device remote-device not found" in result.error


def test_mcp_screenshot_handles_device_not_available_error(
    mcp_env: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unavailable(timeout: int = 10) -> FakeScreenshot:
        raise DeviceNotAvailableError("device temporarily offline")

    mcp_env["manager"]._devices["local-device"].get_screenshot = raise_unavailable

    result = asyncio.run(mcp_api.screenshot("local-device"))

    assert result.model_dump() == {
        "success": False,
        "image": "",
        "width": 0,
        "height": 0,
        "is_sensitive": False,
        "error": "device temporarily offline",
    }
