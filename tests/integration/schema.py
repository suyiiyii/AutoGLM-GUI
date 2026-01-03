"""Pydantic schemas for validating test case YAML configurations."""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class TransitionSchema(BaseModel):
    """Schema for state transition definition."""

    click_region: tuple[int, int, int, int] = Field(
        description="Click region as (x1, y1, x2, y2) in pixels. "
        "Should include any desired tolerance in the boundary."
    )
    next_state: str = Field(description="ID of the next state to transition to")
    description: str = Field(default="", description="Optional description for logging")

    @field_validator("click_region")
    @classmethod
    def validate_click_region(
        cls, v: tuple[int, int, int, int]
    ) -> tuple[int, int, int, int]:
        """Validate click region coordinates."""
        if len(v) != 4:
            raise ValueError("click_region must have exactly 4 values (x1, y1, x2, y2)")

        x1, y1, x2, y2 = v

        if x1 < 0 or y1 < 0:
            raise ValueError("Coordinates must be non-negative")

        if x2 <= x1:
            raise ValueError(f"x2 ({x2}) must be greater than x1 ({x1})")

        if y2 <= y1:
            raise ValueError(f"y2 ({y2}) must be greater than y1 ({y1})")

        return v


class StateSchema(BaseModel):
    """Schema for test state definition."""

    id: str = Field(description="Unique state identifier")
    screenshot: str = Field(description="Path to screenshot file (relative to YAML)")
    current_app: str = Field(
        default="com.android.launcher",
        description="Current app package name for this state",
    )
    transitions: list[TransitionSchema] = Field(
        default_factory=list, description="List of possible transitions from this state"
    )
    is_terminal: bool = Field(
        default=False, description="Whether this is a terminal state"
    )
    expected_finish: bool = Field(
        default=False,
        description="Whether Agent should call finish() in this state",
    )

    @field_validator("screenshot")
    @classmethod
    def validate_screenshot_extension(cls, v: str) -> str:
        """Validate screenshot has valid image extension."""
        valid_extensions = {".png", ".jpg", ".jpeg"}
        ext = Path(v).suffix.lower()
        if ext not in valid_extensions:
            raise ValueError(
                f"Screenshot must have one of {valid_extensions}, got: {ext}"
            )
        return v

    @field_validator("expected_finish")
    @classmethod
    def validate_finish_consistency(cls, v: bool, info) -> bool:
        """Validate that expected_finish is only True for terminal states."""
        # Access other field values through info.data
        is_terminal = info.data.get("is_terminal", False)
        if v and not is_terminal:
            raise ValueError("expected_finish can only be True if is_terminal is True")
        return v


class TestScenarioSchema(BaseModel):
    """Schema for complete test scenario configuration."""

    test_name: str = Field(description="Name of the test scenario")
    instruction: str = Field(
        min_length=1, description="Task instruction to give to the Agent"
    )
    max_steps: int = Field(default=10, ge=1, description="Maximum steps allowed")
    states: list[StateSchema] = Field(
        min_length=1, description="List of states in the test scenario"
    )

    @field_validator("states")
    @classmethod
    def validate_states(cls, v: list[StateSchema]) -> list[StateSchema]:
        """Validate state definitions."""
        if not v:
            raise ValueError("Must define at least one state")

        # Check for duplicate state IDs
        state_ids = [state.id for state in v]
        duplicates = [sid for sid in state_ids if state_ids.count(sid) > 1]
        if duplicates:
            raise ValueError(f"Duplicate state IDs found: {set(duplicates)}")

        # Validate that all next_state references exist
        valid_ids = set(state_ids)
        for state in v:
            for transition in state.transitions:
                if transition.next_state not in valid_ids:
                    raise ValueError(
                        f"State '{state.id}' has transition to undefined state "
                        f"'{transition.next_state}'"
                    )

        # Check that there's at least one terminal state
        terminal_states = [s for s in v if s.is_terminal]
        if not terminal_states:
            raise ValueError("Must have at least one terminal state (is_terminal=true)")

        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "test_name": "微信发送消息",
                    "instruction": "打开微信，给张三发送消息'你好'",
                    "max_steps": 10,
                    "states": [
                        {
                            "id": "home",
                            "screenshot": "state_home.png",
                            "transitions": [
                                {
                                    "click_region": [100, 500, 200, 600],
                                    "next_state": "wechat_main",
                                    "description": "点击微信图标",
                                }
                            ],
                        },
                        {
                            "id": "wechat_main",
                            "screenshot": "state_wechat.png",
                            "is_terminal": True,
                            "expected_finish": True,
                        },
                    ],
                }
            ]
        }
    }
