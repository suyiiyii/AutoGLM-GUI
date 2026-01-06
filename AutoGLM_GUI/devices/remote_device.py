"""Remote Device implementation using HTTP.

This module provides a RemoteDevice that connects to a Device Agent
via HTTP, allowing remote control of devices.
"""

import httpx

from AutoGLM_GUI.device_protocol import (
    DeviceInfo,
    DeviceManagerProtocol,
    DeviceProtocol,
    Screenshot,
)


class RemoteDevice(DeviceProtocol):
    """
    Remote device implementation using HTTP.

    Connects to a Device Agent server that handles actual device operations.
    The server decides the implementation (ADB, Accessibility, Mock, etc.).

    Example:
        >>> device = RemoteDevice("phone_001", "http://localhost:8001")
        >>> screenshot = device.get_screenshot()
        >>> device.tap(100, 200)
    """

    def __init__(self, device_id: str, base_url: str, timeout: float = 30.0):
        self._device_id = device_id
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    @property
    def device_id(self) -> str:
        return self._device_id

    def _post(self, endpoint: str, json: dict | None = None) -> dict:
        """POST request helper."""
        url = f"{self._base_url}/device/{self._device_id}{endpoint}"
        resp = self._client.post(url, json=json or {})
        resp.raise_for_status()
        return resp.json()

    def _get(self, endpoint: str) -> dict:
        """GET request helper."""
        url = f"{self._base_url}/device/{self._device_id}{endpoint}"
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        data = self._post("/screenshot", {"timeout": timeout})
        return Screenshot(
            base64_data=data["base64_data"],
            width=data["width"],
            height=data["height"],
            is_sensitive=data.get("is_sensitive", False),
        )

    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        self._post("/tap", {"x": x, "y": y, "delay": delay})

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        self._post("/double_tap", {"x": x, "y": y, "delay": delay})

    def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        self._post(
            "/long_press", {"x": x, "y": y, "duration_ms": duration_ms, "delay": delay}
        )

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        self._post(
            "/swipe",
            {
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "duration_ms": duration_ms,
                "delay": delay,
            },
        )

    def type_text(self, text: str) -> None:
        self._post("/type_text", {"text": text})

    def clear_text(self) -> None:
        self._post("/clear_text")

    def back(self, delay: float | None = None) -> None:
        self._post("/back", {"delay": delay})

    def home(self, delay: float | None = None) -> None:
        self._post("/home", {"delay": delay})

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        data = self._post("/launch_app", {"app_name": app_name, "delay": delay})
        return data.get("success", True)

    def get_current_app(self) -> str:
        data = self._get("/current_app")
        return data["app_name"]

    def detect_and_set_adb_keyboard(self) -> str:
        data = self._post("/detect_keyboard")
        return data.get("original_ime", "")

    def restore_keyboard(self, ime: str) -> None:
        self._post("/restore_keyboard", {"ime": ime})

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class RemoteDeviceManager(DeviceManagerProtocol):
    """
    Remote device manager using HTTP.

    Manages connections to a Device Agent server.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._devices: dict[str, RemoteDevice] = {}

    def list_devices(self) -> list[DeviceInfo]:
        resp = self._client.get(f"{self._base_url}/devices")
        resp.raise_for_status()
        return [DeviceInfo(**d) for d in resp.json()]

    def get_device(self, device_id: str) -> RemoteDevice:
        if device_id not in self._devices:
            self._devices[device_id] = RemoteDevice(
                device_id, self._base_url, self._timeout
            )
        return self._devices[device_id]

    def connect(self, address: str, timeout: int = 10) -> tuple[bool, str]:
        resp = self._client.post(
            f"{self._base_url}/connect", json={"address": address, "timeout": timeout}
        )
        data = resp.json()
        return data.get("success", False), data.get("message", "")

    def disconnect(self, device_id: str) -> tuple[bool, str]:
        self._devices.pop(device_id, None)
        resp = self._client.post(
            f"{self._base_url}/disconnect", json={"device_id": device_id}
        )
        data = resp.json()
        return data.get("success", True), data.get("message", "Disconnected")

    def close(self) -> None:
        for device in self._devices.values():
            device.close()
        self._client.close()
