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


class ConfigResponse(BaseModel):
    """配置读取响应."""

    base_url: str
    model_name: str
    api_key: str  # 返回实际值（明文）
    source: str  # "CLI arguments" | "environment variables" | "config file (...)" | "default"
    conflicts: list[dict] | None = None  # 配置冲突信息（可选）
    # conflicts 示例：
    # [
    #   {
    #     "field": "base_url",
    #     "file_value": "http://localhost:8080/v1",
    #     "override_value": "https://api.example.com",
    #     "override_source": "CLI arguments"
    #   }
    # ]


class ConfigSaveRequest(BaseModel):
    """配置保存请求."""

    base_url: str
    model_name: str = "autoglm-phone-9b"
    api_key: str | None = None


class WiFiConnectRequest(BaseModel):
    device_id: str | None = None
    port: int = 5555


class WiFiConnectResponse(BaseModel):
    success: bool
    message: str
    device_id: str | None = None
    address: str | None = None
    error: str | None = None


class WiFiDisconnectRequest(BaseModel):
    device_id: str


class WiFiDisconnectResponse(BaseModel):
    success: bool
    message: str
    error: str | None = None


class WiFiManualConnectRequest(BaseModel):
    """手动连接 WiFi 请求 (无需 USB)."""

    ip: str  # IP 地址
    port: int = 5555  # 端口，默认 5555


class WiFiManualConnectResponse(BaseModel):
    """手动连接 WiFi 响应."""

    success: bool
    message: str
    device_id: str | None = None  # 连接后的设备 ID (ip:port)
    error: str | None = None


class WiFiPairRequest(BaseModel):
    """WiFi pairing request (Android 11+ wireless debugging)."""

    ip: str  # Device IP address
    pairing_port: int  # Pairing port (from "Pair device with code" dialog)
    pairing_code: str  # 6-digit pairing code
    connection_port: int = 5555  # Standard ADB connection port (default 5555)


class WiFiPairResponse(BaseModel):
    """WiFi pairing response."""

    success: bool
    message: str
    device_id: str | None = None  # Device ID after connection (ip:connection_port)
    error: str | None = None  # Error code for frontend handling


class VersionCheckResponse(BaseModel):
    """Version update check response."""

    current_version: str
    latest_version: str | None = None
    has_update: bool = False
    release_url: str | None = None
    published_at: str | None = None
    error: str | None = None


class MdnsDeviceResponse(BaseModel):
    """Single mDNS-discovered device."""

    name: str  # Device name (e.g., "adb-243a09b7-cbCO6P")
    ip: str  # IP address
    port: int  # Port number
    has_pairing: bool  # Whether pairing service was also advertised
    service_type: str  # Service type
    pairing_port: int | None = None  # Pairing port if has_pairing is True


class MdnsDiscoverResponse(BaseModel):
    """mDNS device discovery response."""

    success: bool
    devices: list[MdnsDeviceResponse]
    error: str | None = None


# QR Code Pairing Models


class QRPairGenerateResponse(BaseModel):
    """QR code pairing generation response."""

    success: bool
    qr_payload: str | None = (
        None  # QR text payload (WIFI:T:ADB;S:{name};P:{password};;)
    )
    session_id: str | None = None  # Session tracking ID (UUID)
    expires_at: float | None = None  # Unix timestamp when session expires
    message: str
    error: str | None = None  # Error code for frontend handling


class QRPairStatusResponse(BaseModel):
    """QR code pairing status response."""

    session_id: str
    status: str  # "listening" | "pairing" | "paired" | "connecting" | "connected" | "timeout" | "error"
    device_id: str | None = None  # Device ID when connected (ip:port)
    message: str
    error: str | None = None  # Error details


class QRPairCancelResponse(BaseModel):
    """QR code pairing cancellation response."""

    success: bool
    message: str
