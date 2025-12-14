"""Shared Pydantic models for the AutoGLM-GUI API."""

from pydantic import BaseModel, Field


class APIModelConfig(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2


class APIAgentConfig(BaseModel):
    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True


class InitRequest(BaseModel):
    model: APIModelConfig | None = Field(default=None, alias="model_config")
    agent: APIAgentConfig | None = Field(default=None, alias="agent_config")


class ChatRequest(BaseModel):
    message: str
    device_id: str  # 设备 ID（必填）


class ChatResponse(BaseModel):
    result: str
    steps: int
    success: bool


class StatusResponse(BaseModel):
    version: str
    initialized: bool
    step_count: int


class ResetRequest(BaseModel):
    device_id: str  # 设备 ID（必填）


class ScreenshotRequest(BaseModel):
    device_id: str | None = None


class ScreenshotResponse(BaseModel):
    success: bool
    image: str  # base64 encoded PNG
    width: int
    height: int
    is_sensitive: bool
    error: str | None = None


class TapRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TapResponse(BaseModel):
    success: bool
    error: str | None = None


class SwipeRequest(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration_ms: int | None = None
    device_id: str | None = None
    delay: float = 0.0


class SwipeResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchDownRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TouchDownResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchMoveRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TouchMoveResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchUpRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0


class TouchUpResponse(BaseModel):
    success: bool
    error: str | None = None


class DeviceListResponse(BaseModel):
    devices: list[dict]


class ConnectDeviceRequest(BaseModel):
    address: str  # 设备地址，格式: "192.168.1.100:5555" 或 "192.168.1.100"
    timeout: int = 10


class ConnectDeviceResponse(BaseModel):
    success: bool
    message: str


class DisconnectDeviceRequest(BaseModel):
    address: str | None = None  # 如果为 None，断开所有连接


class DisconnectDeviceResponse(BaseModel):
    success: bool
    message: str


class EnableTcpipRequest(BaseModel):
    device_id: str | None = None  # 如果为 None，使用第一个可用设备
    port: int = 5555


class EnableTcpipResponse(BaseModel):
    success: bool
    message: str
    device_ip: str | None = None  # 设备的 IP 地址（如果获取成功）


class GetDeviceIpRequest(BaseModel):
    device_id: str | None = None


class GetDeviceIpResponse(BaseModel):
    success: bool
    ip: str | None = None
    message: str | None = None
