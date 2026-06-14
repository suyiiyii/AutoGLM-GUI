"""Reverse Android Agent device implementation.

This module provides a ReverseAgentDevice that controls an Android Agent
through the reverse WebSocket command channel managed by ReverseAgentRegistry.
"""

from __future__ import annotations

from typing import Any

from AutoGLM_GUI.device_protocol import DeviceProtocol, Screenshot
from AutoGLM_GUI.reverse_agent_protocol import ReverseAgentCommand
from AutoGLM_GUI.reverse_agent_registry import get_reverse_agent_registry
from AutoGLM_GUI.trace import trace_span


class ReverseAgentDevice(DeviceProtocol):
    """Device implementation that controls a reverse-connected Android Agent.

    Commands are sent over the persistent WebSocket channel maintained by
    ReverseAgentRegistry. The Android Agent executes them locally using its
    AccessibilityService and MediaProjection.
    """

    def __init__(self, agent_id: str, timeout_seconds: float = 30.0):
        self._agent_id = agent_id
        self._timeout_seconds = timeout_seconds
        self._registry = get_reverse_agent_registry()

    @property
    def device_id(self) -> str:
        return self._agent_id

    def _send(
        self, command_type: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        command = ReverseAgentCommand.new(
            command_type=command_type,  # type: ignore[arg-type]
            payload=payload,
        )
        with trace_span(
            "reverse_agent_device.send",
            attrs={"agent_id": self._agent_id, "command_type": command_type},
        ):
            # send_command is async, but DeviceProtocol methods are sync.
            # Run the coroutine on the current event loop if one exists,
            # otherwise create a new one.
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(
                    self._registry.send_command(
                        agent_id=self._agent_id,
                        command=command,
                        timeout_seconds=self._timeout_seconds,
                    )
                ).payload

            future = asyncio.run_coroutine_threadsafe(
                self._registry.send_command(
                    agent_id=self._agent_id,
                    command=command,
                    timeout_seconds=self._timeout_seconds,
                ),
                loop,
            )
            return future.result(timeout=self._timeout_seconds + 5).payload

    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        data = self._send("screenshot", {"timeout": timeout})
        return Screenshot(
            base64_data=data["base64_data"],
            width=data["width"],
            height=data["height"],
            is_sensitive=data.get("is_sensitive", False),
        )

    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        self._send("tap", {"x": x, "y": y, "delay": delay})

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        # Reverse agent currently supports atomic tap; double-tap can be added later.
        self._send("tap", {"x": x, "y": y, "delay": delay})

    def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        # Reverse agent swipe can simulate a long press by holding at one point.
        self._send(
            "swipe",
            {
                "start_x": x,
                "start_y": y,
                "end_x": x,
                "end_y": y,
                "duration_ms": duration_ms,
                "delay": delay,
            },
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
        self._send(
            "swipe",
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
        self._send("type_text", {"text": text})

    def clear_text(self) -> None:
        # Not directly supported by the reverse agent command set.
        # Send an empty type_text as a no-op best-effort fallback.
        self._send("type_text", {"text": ""})

    def back(self, delay: float | None = None) -> None:
        # Not supported in the minimal reverse agent command set.
        raise NotImplementedError(
            "ReverseAgentDevice does not support back() in the minimal command set"
        )

    def home(self, delay: float | None = None) -> None:
        # Not supported in the minimal reverse agent command set.
        raise NotImplementedError(
            "ReverseAgentDevice does not support home() in the minimal command set"
        )

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        # Not supported in the minimal reverse agent command set.
        raise NotImplementedError(
            "ReverseAgentDevice does not support launch_app() in the minimal command set"
        )

    def get_current_app(self) -> str:
        data = self._send("current_app")
        return data["app_name"]

    def detect_and_set_adb_keyboard(self) -> str:
        # Reverse agent uses AccessibilityService for text input; ADB keyboard is not needed.
        return ""

    def restore_keyboard(self, ime: str) -> None:
        # No-op for reverse agent.
        return

    def close(self) -> None:
        # Nothing to close; the WebSocket session is managed by the registry.
        return
