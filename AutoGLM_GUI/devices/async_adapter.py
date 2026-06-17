"""Adapter that exposes any sync DeviceProtocol as AsyncDeviceProtocol."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from AutoGLM_GUI.device_protocol import (
    AsyncDeviceProtocol,
    DeviceProtocol,
    Screenshot,
)
from AutoGLM_GUI.trace import trace_span


async def _maybe_await(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call ``fn`` and await it if it returns a coroutine, else run in a thread."""
    if asyncio.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    return await asyncio.to_thread(fn, *args, **kwargs)


class AsyncDeviceAdapter(AsyncDeviceProtocol):
    """
    Wrap any :class:`DeviceProtocol` implementation so it satisfies
    :class:`AsyncDeviceProtocol`.

    This is a compatibility bridge: it keeps agents fully async while allowing
    existing sync device implementations (e.g. :class:`RemoteDevice`) to be
    reused without an immediate rewrite.
    """

    def __init__(self, device: DeviceProtocol | AsyncDeviceProtocol):
        self._device = device

    @property
    def device_id(self) -> str:
        return self._device.device_id

    async def get_screenshot(self, timeout: int = 10) -> Screenshot:
        with trace_span(
            "device_adapter.get_screenshot",
            attrs={"device_id": self.device_id},
        ):
            return await _maybe_await(self._device.get_screenshot, timeout)

    async def tap(self, x: int, y: int, delay: float | None = None) -> None:
        with trace_span(
            "device_adapter.tap",
            attrs={"device_id": self.device_id, "x": x, "y": y},
        ):
            await _maybe_await(self._device.tap, x, y, delay)

    async def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        with trace_span(
            "device_adapter.double_tap",
            attrs={"device_id": self.device_id, "x": x, "y": y},
        ):
            await _maybe_await(self._device.double_tap, x, y, delay)

    async def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        delay: float | None = None,
    ) -> None:
        with trace_span(
            "device_adapter.long_press",
            attrs={"device_id": self.device_id, "x": x, "y": y},
        ):
            await _maybe_await(self._device.long_press, x, y, duration_ms, delay)

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        with trace_span(
            "device_adapter.swipe",
            attrs={"device_id": self.device_id},
        ):
            await _maybe_await(
                self._device.swipe,
                start_x,
                start_y,
                end_x,
                end_y,
                duration_ms,
                delay,
            )

    async def type_text(self, text: str) -> None:
        with trace_span(
            "device_adapter.type_text",
            attrs={"device_id": self.device_id, "text_length": len(text)},
        ):
            await _maybe_await(self._device.type_text, text)

    async def clear_text(self) -> None:
        with trace_span(
            "device_adapter.clear_text",
            attrs={"device_id": self.device_id},
        ):
            await _maybe_await(self._device.clear_text)

    async def back(self, delay: float | None = None) -> None:
        with trace_span(
            "device_adapter.back",
            attrs={"device_id": self.device_id},
        ):
            await _maybe_await(self._device.back, delay)

    async def home(self, delay: float | None = None) -> None:
        with trace_span(
            "device_adapter.home",
            attrs={"device_id": self.device_id},
        ):
            await _maybe_await(self._device.home, delay)

    async def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        with trace_span(
            "device_adapter.launch_app",
            attrs={"device_id": self.device_id, "app_name": app_name},
        ):
            return await _maybe_await(self._device.launch_app, app_name, delay)

    async def get_current_app(self) -> str:
        with trace_span(
            "device_adapter.get_current_app",
            attrs={"device_id": self.device_id},
        ):
            return await _maybe_await(self._device.get_current_app)

    async def detect_and_set_adb_keyboard(self) -> str:
        with trace_span(
            "device_adapter.detect_and_set_adb_keyboard",
            attrs={"device_id": self.device_id},
        ):
            return await _maybe_await(self._device.detect_and_set_adb_keyboard)

    async def restore_keyboard(self, ime: str) -> None:
        with trace_span(
            "device_adapter.restore_keyboard",
            attrs={"device_id": self.device_id},
        ):
            await _maybe_await(self._device.restore_keyboard, ime)

    def __getattr__(self, name: str) -> Any:
        """Forward any other attribute access to the wrapped device."""
        return getattr(self._device, name)
