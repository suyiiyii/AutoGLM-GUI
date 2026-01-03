"""Mock Device Agent Server for integration testing.

This FastAPI server simulates a Device Agent, recording all commands
for later assertion in tests. It can be backed by a state machine
for realistic screenshot responses.

Usage:
    # Start the server
    uvicorn tests.integration.device_agent.mock_agent_server:app --port 8001

    # Or programmatically
    from tests.integration.device_agent.mock_agent_server import create_app
    app = create_app(scenario_path="scenarios/meituan_message/scenario.yaml")
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


@dataclass
class CommandRecord:
    """Record of a single command received by the agent."""

    action: str
    device_id: str
    params: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "device_id": self.device_id,
            "params": self.params,
            "timestamp": self.timestamp.isoformat(),
        }


class MockAgentState:
    """Global state for the mock agent."""

    def __init__(self):
        self.commands: list[CommandRecord] = []
        self.state_machine = None
        self.scenario_path: str | None = None

    def record(self, action: str, device_id: str, **params):
        """Record a command."""
        self.commands.append(
            CommandRecord(
                action=action,
                device_id=device_id,
                params=params,
            )
        )

    def reset(self):
        """Reset command history."""
        self.commands = []

    def load_scenario(self, path: str | Path):
        """Load a test scenario (state machine)."""
        from tests.integration.state_machine import load_test_case

        self.scenario_path = str(path)
        self.state_machine, _, _ = load_test_case(path)

    def get_screenshot_data(self) -> dict:
        """Get current screenshot from state machine or return placeholder."""
        if self.state_machine:
            result = self.state_machine.get_current_screenshot()
            return {
                "base64_data": result.base64_data,
                "width": result.width,
                "height": result.height,
                "is_sensitive": False,
            }
        return {
            "base64_data": "",
            "width": 1080,
            "height": 2400,
            "is_sensitive": False,
        }

    def get_current_app(self) -> str:
        """Get current app from state machine."""
        if self.state_machine:
            return self.state_machine.current_state.current_app
        return "com.mock.app"


state = MockAgentState()


class TapRequest(BaseModel):
    x: int
    y: int
    delay: float | None = None


class SwipeRequest(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration_ms: int | None = None
    delay: float | None = None


class LongPressRequest(BaseModel):
    x: int
    y: int
    duration_ms: int = 3000
    delay: float | None = None


class TypeTextRequest(BaseModel):
    text: str


class LaunchAppRequest(BaseModel):
    app_name: str
    delay: float | None = None


class ScreenshotRequest(BaseModel):
    timeout: int = 10


class LoadScenarioRequest(BaseModel):
    scenario_path: str


def create_app(scenario_path: str | None = None) -> FastAPI:
    """Create the FastAPI app with optional pre-loaded scenario."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if scenario_path:
            state.load_scenario(scenario_path)
        yield

    app = FastAPI(
        title="Mock Device Agent",
        description="Mock device agent for integration testing",
        lifespan=lifespan,
    )

    _register_routes(app)
    return app


def _register_routes(app: FastAPI):
    """Register all routes on the app."""

    # === Device List ===
    @app.get("/devices")
    async def list_devices():
        """List available mock devices."""
        return [
            {
                "device_id": "mock_device_001",
                "status": "online",
                "model": "MockPhone",
                "platform": "android",
                "connection_type": "mock",
            }
        ]

    # === Screenshot ===
    @app.post("/device/{device_id}/screenshot")
    async def screenshot(device_id: str, req: ScreenshotRequest):
        state.record("screenshot", device_id, timeout=req.timeout)
        return state.get_screenshot_data()

    # === Input Operations ===
    @app.post("/device/{device_id}/tap")
    async def tap(device_id: str, req: TapRequest):
        state.record("tap", device_id, x=req.x, y=req.y, delay=req.delay)
        if state.state_machine:
            state.state_machine.handle_tap(req.x, req.y)
        return {"status": "ok"}

    @app.post("/device/{device_id}/double_tap")
    async def double_tap(device_id: str, req: TapRequest):
        state.record("double_tap", device_id, x=req.x, y=req.y, delay=req.delay)
        if state.state_machine:
            state.state_machine.handle_tap(req.x, req.y)
        return {"status": "ok"}

    @app.post("/device/{device_id}/long_press")
    async def long_press(device_id: str, req: LongPressRequest):
        state.record(
            "long_press",
            device_id,
            x=req.x,
            y=req.y,
            duration_ms=req.duration_ms,
            delay=req.delay,
        )
        if state.state_machine:
            state.state_machine.handle_tap(req.x, req.y)
        return {"status": "ok"}

    @app.post("/device/{device_id}/swipe")
    async def swipe(device_id: str, req: SwipeRequest):
        state.record(
            "swipe",
            device_id,
            start_x=req.start_x,
            start_y=req.start_y,
            end_x=req.end_x,
            end_y=req.end_y,
            duration_ms=req.duration_ms,
            delay=req.delay,
        )
        if state.state_machine:
            state.state_machine.handle_swipe(
                req.start_x, req.start_y, req.end_x, req.end_y
            )
        return {"status": "ok"}

    @app.post("/device/{device_id}/type_text")
    async def type_text(device_id: str, req: TypeTextRequest):
        state.record("type_text", device_id, text=req.text)
        return {"status": "ok"}

    @app.post("/device/{device_id}/clear_text")
    async def clear_text(device_id: str):
        state.record("clear_text", device_id)
        return {"status": "ok"}

    # === Navigation ===
    @app.post("/device/{device_id}/back")
    async def back(device_id: str, delay: float | None = None):
        state.record("back", device_id, delay=delay)
        return {"status": "ok"}

    @app.post("/device/{device_id}/home")
    async def home(device_id: str, delay: float | None = None):
        state.record("home", device_id, delay=delay)
        return {"status": "ok"}

    @app.post("/device/{device_id}/launch_app")
    async def launch_app(device_id: str, req: LaunchAppRequest):
        state.record("launch_app", device_id, app_name=req.app_name, delay=req.delay)
        return {"status": "ok", "success": True}

    # === State Query ===
    @app.get("/device/{device_id}/current_app")
    async def current_app(device_id: str):
        state.record("get_current_app", device_id)
        return {"app_name": state.get_current_app()}

    # === Keyboard ===
    @app.post("/device/{device_id}/detect_keyboard")
    async def detect_keyboard(device_id: str):
        state.record("detect_keyboard", device_id)
        return {"original_ime": "com.mock.keyboard"}

    @app.post("/device/{device_id}/restore_keyboard")
    async def restore_keyboard(device_id: str, ime: str = ""):
        state.record("restore_keyboard", device_id, ime=ime)
        return {"status": "ok"}

    # === Test Assertion APIs ===
    @app.get("/test/commands")
    async def get_commands():
        """Get all recorded commands for assertion."""
        return [cmd.to_dict() for cmd in state.commands]

    @app.get("/test/commands/actions")
    async def get_command_actions():
        """Get simplified list of actions only."""
        return [{"action": cmd.action, **cmd.params} for cmd in state.commands]

    @app.post("/test/reset")
    async def reset():
        """Reset command history."""
        state.reset()
        return {"status": "reset", "commands_cleared": True}

    @app.post("/test/load_scenario")
    async def load_scenario(req: LoadScenarioRequest):
        """Load a test scenario (state machine)."""
        try:
            state.load_scenario(req.scenario_path)
            return {
                "status": "loaded",
                "scenario": req.scenario_path,
                "states": list(state.state_machine.states.keys())
                if state.state_machine
                else [],
            }
        except Exception as e:
            raise HTTPException(400, f"Failed to load scenario: {e}")

    @app.get("/test/state")
    async def get_state():
        """Get current state machine state."""
        if not state.state_machine:
            return {"current_state": None, "history": []}
        return {
            "current_state": state.state_machine.current_state_id,
            "history": state.state_machine.state_history,
        }

    @app.get("/test/expect")
    async def expect_commands(actions: str):
        """
        Verify expected command sequence.

        Args:
            actions: Comma-separated list of expected actions (e.g., "tap,swipe,tap")

        Returns:
            Match result with details.
        """
        expected = [a.strip() for a in actions.split(",")]
        actual = [cmd.action for cmd in state.commands]

        match = actual == expected
        return {
            "match": match,
            "expected": expected,
            "actual": actual,
            "message": "Commands match!"
            if match
            else f"Mismatch: expected {expected}, got {actual}",
        }


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
