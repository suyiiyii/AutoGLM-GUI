"""Shared Pydantic models for the AutoGLM-GUI API."""

import re

from pydantic import BaseModel, Field, field_validator


class APIModelConfig(BaseModel):
    """API layer model configuration (Pydantic).

    This will be converted to AutoGLM_GUI.config.ModelConfig internally.
    """

    base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        """验证 base_url 格式."""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # 检查是否是有效的 HTTP/HTTPS URL
        if not re.match(r"^https?://", v):
            raise ValueError("base_url must start with http:// or https://")
        return v


class APIAgentConfig(BaseModel):
    """API layer agent configuration (Pydantic).

    This will be converted to AutoGLM_GUI.config.AgentConfig internally.
    """

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True

    @field_validator("max_steps")
    @classmethod
    def validate_max_steps(cls, v: int) -> int:
        """验证 max_steps 范围."""
        if v <= 0:
            raise ValueError("max_steps must be positive")
        if v > 1000:
            raise ValueError("max_steps must be <= 1000")
        return v

    @field_validator("lang")
    @classmethod
    def validate_lang(cls, v: str) -> str:
        """验证 lang 有效性."""
        allowed_langs = ["cn", "en"]
        if v not in allowed_langs:
            raise ValueError(f"lang must be one of {allowed_langs}")
        return v


class InitRequest(BaseModel):
    model: APIModelConfig | None = Field(default=None, alias="model_config")
    agent: APIAgentConfig | None = Field(default=None, alias="agent_config")

    # Agent configuration (factory pattern)
    agent_type: str = "glm"  # Agent type to use (e.g., "glm", "mai")
    agent_config_params: dict | None = None  # Agent-specific configuration parameters

    # Hot-reload support
    force: bool = False  # Force re-initialization even if agent already exists

    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v: str) -> str:
        """验证 agent_type 有效性."""
        # Don't import at module level to avoid circular imports
        from AutoGLM_GUI.agents import is_agent_type_registered

        if not is_agent_type_registered(v):
            raise ValueError(
                f"Unknown agent_type: '{v}'. "
                f"Please register the agent type first or use a known type."
            )
        return v


class ChatRequest(BaseModel):
    message: str
    device_id: str  # 设备 ID（必填）

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """验证 message 非空."""
        if not v or not v.strip():
            raise ValueError("message cannot be empty")
        if len(v) > 10000:
            raise ValueError("message too long (max 10000 characters)")
        return v.strip()


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


class AbortRequest(BaseModel):
    """中断对话请求。"""

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

    @field_validator("x", "y")
    @classmethod
    def validate_coordinates(cls, v: int) -> int:
        """验证坐标范围."""
        if v < 0:
            raise ValueError("coordinates must be non-negative")
        if v > 10000:  # 合理的最大屏幕尺寸
            raise ValueError("coordinates must be <= 10000")
        return v

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, v: float) -> float:
        """验证 delay 范围."""
        if v < 0.0:
            raise ValueError("delay must be non-negative")
        if v > 60.0:  # 最大等待 60 秒
            raise ValueError("delay must be <= 60.0 seconds")
        return v


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

    @field_validator("start_x", "start_y", "end_x", "end_y")
    @classmethod
    def validate_coordinates(cls, v: int) -> int:
        """验证坐标范围."""
        if v < 0:
            raise ValueError("coordinates must be non-negative")
        if v > 10000:
            raise ValueError("coordinates must be <= 10000")
        return v

    @field_validator("duration_ms")
    @classmethod
    def validate_duration(cls, v: int | None) -> int | None:
        """验证滑动持续时间."""
        if v is not None:
            if v < 0:
                raise ValueError("duration_ms must be non-negative")
            if v > 10000:  # 最大 10 秒
                raise ValueError("duration_ms must be <= 10000")
        return v

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, v: float) -> float:
        """验证 delay 范围."""
        if v < 0.0:
            raise ValueError("delay must be non-negative")
        if v > 60.0:
            raise ValueError("delay must be <= 60.0 seconds")
        return v


class SwipeResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchDownRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0

    @field_validator("x", "y")
    @classmethod
    def validate_coordinates(cls, v: int) -> int:
        """验证坐标范围."""
        if v < 0:
            raise ValueError("coordinates must be non-negative")
        if v > 10000:
            raise ValueError("coordinates must be <= 10000")
        return v

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, v: float) -> float:
        """验证 delay 范围."""
        if v < 0.0:
            raise ValueError("delay must be non-negative")
        if v > 60.0:
            raise ValueError("delay must be <= 60.0 seconds")
        return v


class TouchDownResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchMoveRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0

    @field_validator("x", "y")
    @classmethod
    def validate_coordinates(cls, v: int) -> int:
        """验证坐标范围."""
        if v < 0:
            raise ValueError("coordinates must be non-negative")
        if v > 10000:
            raise ValueError("coordinates must be <= 10000")
        return v

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, v: float) -> float:
        """验证 delay 范围."""
        if v < 0.0:
            raise ValueError("delay must be non-negative")
        if v > 60.0:
            raise ValueError("delay must be <= 60.0 seconds")
        return v


class TouchMoveResponse(BaseModel):
    success: bool
    error: str | None = None


class TouchUpRequest(BaseModel):
    x: int
    y: int
    device_id: str | None = None
    delay: float = 0.0

    @field_validator("x", "y")
    @classmethod
    def validate_coordinates(cls, v: int) -> int:
        """验证坐标范围."""
        if v < 0:
            raise ValueError("coordinates must be non-negative")
        if v > 10000:
            raise ValueError("coordinates must be <= 10000")
        return v

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, v: float) -> float:
        """验证 delay 范围."""
        if v < 0.0:
            raise ValueError("delay must be non-negative")
        if v > 60.0:
            raise ValueError("delay must be <= 60.0 seconds")
        return v


class TouchUpResponse(BaseModel):
    success: bool
    error: str | None = None


class AgentStatusResponse(BaseModel):
    """Agent 运行状态信息."""

    state: str  # "idle" | "busy" | "error" | "initializing"
    created_at: float  # Unix 时间戳
    last_used: float  # Unix 时间戳
    error_message: str | None = None
    model_name: str  # 来自 ModelConfig


class DeviceResponse(BaseModel):
    """设备信息及可选的 Agent 状态."""

    id: str
    serial: str
    model: str
    status: str
    connection_type: str
    state: str
    is_available_only: bool
    agent: AgentStatusResponse | None = None


class DeviceListResponse(BaseModel):
    devices: list[DeviceResponse]  # 从 list[dict] 改为强类型


class ConfigResponse(BaseModel):
    """配置读取响应."""

    base_url: str
    model_name: str
    api_key: str  # 返回实际值（明文）
    source: str  # "CLI arguments" | "environment variables" | "config file (...)" | "default"

    # Agent 类型配置
    agent_type: str = "glm"  # Agent type (e.g., "glm", "mai")
    agent_config_params: dict | None = None  # Agent-specific configuration

    # Agent 执行配置
    default_max_steps: int = 100  # 单次任务最大执行步数

    conflicts: list[dict] | None = None  # 配置冲突信息（可选）


class ConfigSaveRequest(BaseModel):
    """配置保存请求."""

    base_url: str
    model_name: str = "autoglm-phone-9b"
    api_key: str | None = None

    # Agent 类型配置
    agent_type: str = "glm"  # Agent type to use (e.g., "glm", "mai")
    agent_config_params: dict | None = None  # Agent-specific configuration parameters

    # Agent 执行配置
    default_max_steps: int | None = None  # 单次任务最大执行步数

    @field_validator("default_max_steps")
    @classmethod
    def validate_default_max_steps(cls, v: int | None) -> int | None:
        """验证 default_max_steps 范围."""
        if v is None:
            return v
        if v <= 0:
            raise ValueError("default_max_steps must be positive")
        if v > 1000:
            raise ValueError("default_max_steps must be <= 1000")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """验证 base_url 格式."""
        v = v.strip()
        if not v:
            raise ValueError("base_url cannot be empty")
        if not re.match(r"^https?://", v):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """验证 model_name 非空."""
        if not v or not v.strip():
            raise ValueError("model_name cannot be empty")
        return v.strip()


class WiFiConnectRequest(BaseModel):
    device_id: str | None = None
    port: int = 5555

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """验证端口范围."""
        if v < 1 or v > 65535:
            raise ValueError("port must be between 1 and 65535")
        return v


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

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """验证 IP 地址格式."""
        v = v.strip()
        # 简单的 IPv4 格式验证
        ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        if not re.match(ip_pattern, v):
            raise ValueError("invalid IPv4 address format")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """验证端口范围."""
        if v < 1 or v > 65535:
            raise ValueError("port must be between 1 and 65535")
        return v


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

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """验证 IP 地址格式."""
        v = v.strip()
        ip_pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        if not re.match(ip_pattern, v):
            raise ValueError("invalid IPv4 address format")
        return v

    @field_validator("pairing_port", "connection_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """验证端口范围."""
        if v < 1 or v > 65535:
            raise ValueError("port must be between 1 and 65535")
        return v

    @field_validator("pairing_code")
    @classmethod
    def validate_pairing_code(cls, v: str) -> str:
        """验证配对码格式."""
        v = v.strip()
        if not re.match(r"^\d{6}$", v):
            raise ValueError("pairing_code must be a 6-digit number")
        return v


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


# Workflow Models


class WorkflowBase(BaseModel):
    """Workflow 基础模型."""

    name: str
    text: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """验证 name 非空."""
        if not v or not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """验证 text 非空."""
        if not v or not v.strip():
            raise ValueError("text cannot be empty")
        return v.strip()


class WorkflowCreate(WorkflowBase):
    """创建 Workflow 请求."""

    pass


class WorkflowUpdate(WorkflowBase):
    """更新 Workflow 请求."""

    pass


class WorkflowResponse(WorkflowBase):
    """Workflow 响应."""

    uuid: str


class WorkflowListResponse(BaseModel):
    """Workflow 列表响应."""

    workflows: list[WorkflowResponse]


class RemoteDeviceInfo(BaseModel):
    """远程设备信息."""

    device_id: str
    model: str
    platform: str
    status: str


class RemoteDeviceDiscoverRequest(BaseModel):
    """远程设备发现请求."""

    base_url: str
    timeout: int = 5

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("timeout must be positive")
        if v > 30:
            raise ValueError("timeout must be <= 30 seconds")
        return v


class RemoteDeviceDiscoverResponse(BaseModel):
    """远程设备发现响应."""

    success: bool
    devices: list[RemoteDeviceInfo]
    message: str
    error: str | None = None


class RemoteDeviceAddRequest(BaseModel):
    """添加远程设备请求."""

    base_url: str
    device_id: str

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("device_id cannot be empty")
        if len(v) > 100:
            raise ValueError("device_id too long (max 100 characters)")
        return v


class RemoteDeviceAddResponse(BaseModel):
    """添加远程设备响应."""

    success: bool
    message: str
    serial: str | None = None
    error: str | None = None


class RemoteDeviceRemoveRequest(BaseModel):
    """移除远程设备请求."""

    serial: str


class RemoteDeviceRemoveResponse(BaseModel):
    """移除远程设备响应."""

    success: bool
    message: str
    error: str | None = None
