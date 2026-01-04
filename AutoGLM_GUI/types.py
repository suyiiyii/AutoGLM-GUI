from __future__ import annotations

from enum import Enum
from typing import Literal

from typing_extensions import TypedDict

ActionMetadata = Literal["do", "finish", "takeover"]
PhoneActionType = Literal[
    "Tap", "Swipe", "Type", "Launch", "Wait", "Back", "Home", "Long Press", "Double Tap"
]
MAIActionType = Literal[
    "click",
    "swipe",
    "type",
    "terminate",
    "answer",
    "wait",
    "long_press",
    "double_click",
    "open",
    "system_button",
    "drag",
]
SwipeDirection = Literal["up", "down", "left", "right"]
SystemButton = Literal["back", "home", "enter"]
TerminateStatus = Literal["success", "failure"]
MessageRole = Literal["system", "user", "assistant"]
ContentType = Literal["text", "image_url"]


class PhoneAgentAction(TypedDict, total=False):
    _metadata: ActionMetadata
    action: PhoneActionType
    element: list[int]
    text: str
    app: str
    start: list[int]
    end: list[int]
    duration: str
    message: str


class MAIAction(TypedDict, total=False):
    action: MAIActionType
    coordinate: list[float]
    direction: SwipeDirection
    text: str
    button: SystemButton
    status: TerminateStatus
    start_coordinate: list[float]
    end_coordinate: list[float]


class SSEThinkingChunkData(TypedDict):
    type: str
    role: str
    chunk: str


class SSEStepData(TypedDict, total=False):
    type: str
    role: str
    step: int
    thinking: str
    action: PhoneAgentAction | None
    success: bool
    finished: bool


class SSEDoneData(TypedDict, total=False):
    type: str
    role: str
    message: str
    steps: int
    success: bool


class SSEErrorData(TypedDict):
    type: str
    role: str
    message: str


SSEEventData = SSEThinkingChunkData | SSEStepData | SSEDoneData | SSEErrorData


class MAIAgentSpecificConfig(TypedDict, total=False):
    history_n: int
    max_pixels: int
    min_pixels: int
    tools: list[dict[str, str]]
    use_mai_prompt: bool


class GLMAgentSpecificConfig(TypedDict, total=False):
    pass


AgentSpecificConfig = MAIAgentSpecificConfig | GLMAgentSpecificConfig


class TextContent(TypedDict):
    type: ContentType
    text: str


class ImageURLContent(TypedDict):
    type: ContentType
    image_url: dict[str, str]


MessageContent = str | list[TextContent | ImageURLContent]


class ChatMessage(TypedDict, total=False):
    role: MessageRole
    content: MessageContent


ConversationContext = list[ChatMessage]


class Observation(TypedDict, total=False):
    screenshot: object
    accessibility_tree: dict[str, object] | None


class DeviceConnectionType(Enum):
    """Device connection type.

    Unified enum for device connection types to avoid confusion
    with phone_agent's ConnectionType.

    - USB: Physical USB connection
    - WIFI: ADB over WiFi (local network)
    - REMOTE: HTTP Remote Device (via Device Agent Server)
    """

    USB = "usb"
    WIFI = "wifi"
    REMOTE = "remote"
