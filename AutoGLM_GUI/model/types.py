"""Type definitions for model interactions."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisionModelConfig:
    """Configuration for the vision-language model.

    This follows OpenAI-compatible API standards, supporting any endpoint
    that implements the OpenAI chat completions format.

    Attributes:
        base_url: API endpoint URL (e.g., "http://localhost:8000/v1")
        model_name: Model identifier (e.g., "autoglm-phone")
        api_key: API authentication key (optional for local deployments)
        max_tokens: Maximum tokens in response (default: 2048)
        temperature: Sampling temperature 0-1 (default: 0.01)
        top_p: Nucleus sampling threshold (default: 0.9)
        frequency_penalty: Frequency penalty -2 to 2 (default: 0.0)
        extra_body: Additional parameters for specific backends
        timeout: Request timeout in seconds (default: 120)
    """

    base_url: str
    model_name: str = "autoglm-phone"
    api_key: str = "EMPTY"
    max_tokens: int = 2048
    temperature: float = 0.01
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    extra_body: dict[str, Any] = field(default_factory=dict)
    timeout: int = 120


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
