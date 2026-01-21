"""Type definitions for model interactions."""

from dataclasses import dataclass


@dataclass
class ModelResponse:
    """Response from the vision-language model.

    Attributes:
        thinking: The model's reasoning process (from <think> tag)
        action: The action to execute (from <answer> tag)
        raw_content: Full response text from the model
        time_to_first_token: Time until first token received (seconds)
        time_to_thinking_end: Time until thinking phase completed (seconds)
        total_time: Total inference time (seconds)
    """

    thinking: str
    action: str
    raw_content: str
    time_to_first_token: float | None = None
    time_to_thinking_end: float | None = None
    total_time: float | None = None
