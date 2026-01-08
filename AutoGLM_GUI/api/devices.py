"""Device discovery routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from AutoGLM_GUI.device_manager import ManagedDevice
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

from AutoGLM_GUI.adb_plus.qr_pair import qr_pairing_manager
from AutoGLM_GUI.logger import logger

from AutoGLM_GUI.schemas import (
    DeviceListResponse,
    DeviceResponse,
    MdnsDeviceResponse,
    MdnsDiscoverResponse,
    QRPairCancelResponse,
    QRPairGenerateResponse,
    QRPairStatusResponse,
    RemoteDeviceAddRequest,
    RemoteDeviceAddResponse,
    RemoteDeviceDiscoverRequest,
    RemoteDeviceDiscoverResponse,
    RemoteDeviceInfo,
    RemoteDeviceRemoveRequest,
    RemoteDeviceRemoveResponse,
    WiFiConnectRequest,
    WiFiConnectResponse,
    WiFiDisconnectRequest,
    WiFiDisconnectResponse,
    WiFiManualConnectRequest,
    WiFiManualConnectResponse,
    WiFiPairRequest,
    WiFiPairResponse,
)


def _build_device_response_with_agent(
    device: "ManagedDevice", agent_manager: "PhoneAgentManager"
) -> DeviceResponse:
    """聚合设备信息和 Agent 状态（API 层职责）.

    API 层负责协调 DeviceManager 和 PhoneAgentManager，
    通过遍历设备的所有连接来查找已初始化的 Agent。
    """

    response = device.to_dict()

    # 遍历设备的所有连接，查找已初始化的 Agent
    # 使用 device.connections 公开属性（ManagedDevice 提供）
    for conn in device.connections:
        # 只调用 PhoneAgentManager 的公开方法
        metadata = agent_manager.get_metadata(conn.device_id)
        if metadata:
            # 找到了已初始化的 Agent
            response["agent"] = {
                "state": metadata.state,  # AgentState is str, Enum, already a string
                "created_at": metadata.created_at,
                "last_used": metadata.last_used,
                "error_message": metadata.error_message,
                "model_name": metadata.model_config.model_name,
            }

            break  # 找到第一个 Agent 即可退出
    else:
        # 没有找到任何已初始化的 Agent
        response["agent"] = None

    return DeviceResponse.model_validate(response)


router = APIRouter()


@router.get("/api/devices", response_model=DeviceListResponse)
def list_devices() -> DeviceListResponse:
    """列出所有 ADB 设备及 Agent 状态."""
    from AutoGLM_GUI.device_manager import DeviceManager
    from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager

    device_manager = DeviceManager.get_instance()
    agent_manager = PhoneAgentManager.get_instance()

    # Fallback: 如果轮询未启动,执行同步获取
    if not device_manager._poll_thread or not device_manager._poll_thread.is_alive():
        logger.warning("Polling not started, performing synchronous device fetch")
        device_manager.force_refresh()

    managed_devices = device_manager.get_devices()

    # API 层负责聚合设备信息和 Agent 状态
    devices_with_agents = [
        _build_device_response_with_agent(d, agent_manager) for d in managed_devices
    ]

    return DeviceListResponse(devices=devices_with_agents)


@router.post("/api/devices/connect_wifi", response_model=WiFiConnectResponse)
def connect_wifi(request: WiFiConnectRequest) -> WiFiConnectResponse:
    from AutoGLM_GUI.device_manager import DeviceManager

    if not request.device_id:
        return WiFiConnectResponse(
            success=False,
            message="device_id is required",
            error="device_not_found",
        )

    device_manager = DeviceManager.get_instance()
    success, message, wifi_id = device_manager.connect_wifi(
        device_id=request.device_id,
        port=request.port,
    )

    if success:
        # Immediately refresh device list to show new WiFi device
        device_manager.force_refresh()

        return WiFiConnectResponse(
            success=True,
            message=message,
            device_id=wifi_id,
            address=wifi_id,
        )
    else:
        # Determine error type from message
        error_type = "connect"
        if "not found" in message.lower():
            error_type = "device_not_found"
        elif "tcpip" in message.lower():
            error_type = "tcpip"
        elif "ip" in message.lower():
            error_type = "ip"

        return WiFiConnectResponse(
            success=False,
            message=message,
            error=error_type,
        )


@router.post("/api/devices/disconnect_wifi", response_model=WiFiDisconnectResponse)
def disconnect_wifi(request: WiFiDisconnectRequest) -> WiFiDisconnectResponse:
    """断开 WiFi 连接。"""
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    success, message = device_manager.disconnect_wifi(request.device_id)

    if success:
        # Refresh device list to update status
        device_manager.force_refresh()

    return WiFiDisconnectResponse(
        success=success,
        message=message,
        error=None if success else "disconnect_failed",
    )


@router.post(
    "/api/devices/connect_wifi_manual", response_model=WiFiManualConnectResponse
)
def connect_wifi_manual(
    request: WiFiManualConnectRequest,
) -> WiFiManualConnectResponse:
    """手动连接到 WiFi 设备 (直接连接,无需 USB)."""
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    success, message, device_id = device_manager.connect_wifi_manual(
        ip=request.ip,
        port=request.port,
    )

    if success:
        # Refresh device list to show new device
        device_manager.force_refresh()

        return WiFiManualConnectResponse(
            success=True,
            message=message,
            device_id=device_id,
        )
    else:
        # Determine error type from message
        error_type = "connect_failed"
        if "Invalid IP" in message:
            error_type = "invalid_ip"
        elif "Port must be" in message:
            error_type = "invalid_port"

        return WiFiManualConnectResponse(
            success=False,
            message=message,
            error=error_type,
        )


@router.post("/api/devices/pair_wifi", response_model=WiFiPairResponse)
def pair_wifi(request: WiFiPairRequest) -> WiFiPairResponse:
    """使用无线调试配对并连接到 WiFi 设备 (Android 11+)."""
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    success, message, device_id = device_manager.pair_wifi(
        ip=request.ip,
        pairing_port=request.pairing_port,
        pairing_code=request.pairing_code,
        connection_port=request.connection_port,
    )

    if success:
        # Refresh device list to show newly paired device
        device_manager.force_refresh()

        return WiFiPairResponse(
            success=True,
            message=message,
            device_id=device_id,
        )
    else:
        # Determine error type from message
        error_type = "connect_failed"
        if "Invalid IP" in message:
            error_type = "invalid_ip"
        elif "port must be" in message.lower():
            error_type = "invalid_port"
        elif "Pairing code must be" in message:
            error_type = "invalid_pairing_code"
        elif "connection failed" not in message.lower():
            error_type = "pair_failed"

        return WiFiPairResponse(
            success=False,
            message=message,
            error=error_type,
        )


@router.get("/api/devices/discover_mdns", response_model=MdnsDiscoverResponse)
def discover_mdns() -> MdnsDiscoverResponse:
    """Discover wireless ADB devices via mDNS."""
    from AutoGLM_GUI.adb import ADBConnection
    from AutoGLM_GUI.adb_plus import discover_mdns_devices

    try:
        conn = ADBConnection()
        devices = discover_mdns_devices(conn.adb_path)

        device_responses = [
            MdnsDeviceResponse(
                name=dev.name,
                ip=dev.ip,
                port=dev.port,
                has_pairing=dev.has_pairing,
                service_type=dev.service_type,
                pairing_port=dev.pairing_port,
            )
            for dev in devices
        ]

        return MdnsDiscoverResponse(
            success=True,
            devices=device_responses,
        )

    except Exception as e:
        return MdnsDiscoverResponse(
            success=False,
            devices=[],
            error=str(e),
        )


# QR Code Pairing Routes


@router.post("/api/devices/qr_pair/generate", response_model=QRPairGenerateResponse)
def generate_qr_pairing(timeout: int = 90) -> QRPairGenerateResponse:
    """Generate QR code for wireless pairing and start mDNS listener.

    Args:
        timeout: Session timeout in seconds (default 90)

    Returns:
        QR code payload and session information
    """
    try:
        from AutoGLM_GUI.adb import ADBConnection

        conn = ADBConnection()
        session = qr_pairing_manager.create_session(
            timeout=timeout, adb_path=conn.adb_path
        )

        return QRPairGenerateResponse(
            success=True,
            qr_payload=session.qr_payload,
            session_id=session.session_id,
            expires_at=session.expires_at,
            message="QR code generated, listening for devices...",
        )
    except Exception as e:
        return QRPairGenerateResponse(
            success=False,
            message=f"Failed to generate QR pairing: {str(e)}",
            error="generation_failed",
        )


def _get_status_message(status: str) -> str:
    """Get user-friendly message for status code."""
    messages = {
        "listening": "等待手机扫描二维码...",
        "pairing": "正在配对设备...",
        "paired": "配对成功，正在连接...",
        "connecting": "正在建立连接...",
        "connected": "连接成功！",
        "timeout": "超时：未检测到设备扫码",
        "error": "配对失败",
    }
    return messages.get(status, "未知状态")


@router.get(
    "/api/devices/qr_pair/status/{session_id}", response_model=QRPairStatusResponse
)
def get_qr_pairing_status(session_id: str) -> QRPairStatusResponse:
    """Get current status of a QR pairing session.

    Args:
        session_id: Session UUID

    Returns:
        Current session status and device information if connected
    """
    session = qr_pairing_manager.get_session(session_id)

    if not session:
        return QRPairStatusResponse(
            session_id=session_id,
            status="error",
            message="Session not found or expired",
            error="session_not_found",
        )

    return QRPairStatusResponse(
        session_id=session.session_id,
        status=session.status,
        device_id=session.device_id,
        message=_get_status_message(session.status),
        error=session.error_message,
    )


@router.delete("/api/devices/qr_pair/{session_id}", response_model=QRPairCancelResponse)
def cancel_qr_pairing(session_id: str) -> QRPairCancelResponse:
    """Cancel an active QR pairing session.

    Args:
        session_id: Session UUID to cancel

    Returns:
        Success status
    """
    success = qr_pairing_manager.cancel_session(session_id)

    if success:
        return QRPairCancelResponse(
            success=True,
            message="Pairing session cancelled",
        )
    else:
        return QRPairCancelResponse(
            success=False,
            message="Session not found or already completed",
        )


@router.post(
    "/api/devices/discover_remote", response_model=RemoteDeviceDiscoverResponse
)
def discover_remote_devices(
    request: RemoteDeviceDiscoverRequest,
) -> RemoteDeviceDiscoverResponse:
    """Discover devices from a remote Device Agent Server."""
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    success, message, devices_list = device_manager.discover_remote_devices(
        base_url=request.base_url,
        timeout=request.timeout,
    )

    devices = [RemoteDeviceInfo(**d) for d in devices_list]

    return RemoteDeviceDiscoverResponse(
        success=success,
        devices=devices,
        message=message,
        error=None if success else message,
    )


@router.post("/api/devices/add_remote", response_model=RemoteDeviceAddResponse)
def add_remote_device(request: RemoteDeviceAddRequest) -> RemoteDeviceAddResponse:
    """Add a remote HTTP proxy device manually."""
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    success, message, serial = device_manager.add_remote_device(
        base_url=request.base_url,
        device_id=request.device_id,
    )

    if success:
        return RemoteDeviceAddResponse(
            success=True,
            message=message,
            serial=serial,
        )
    else:
        error_type = "add_failed"
        if "already exists" in message.lower():
            error_type = "already_exists"
        elif "connection failed" in message.lower():
            error_type = "connection_failed"

        return RemoteDeviceAddResponse(
            success=False,
            message=message,
            error=error_type,
        )


@router.post("/api/devices/remove_remote", response_model=RemoteDeviceRemoveResponse)
def remove_remote_device(
    request: RemoteDeviceRemoveRequest,
) -> RemoteDeviceRemoveResponse:
    """Remove a remote device."""
    from AutoGLM_GUI.device_manager import DeviceManager

    device_manager = DeviceManager.get_instance()
    success, message = device_manager.remove_remote_device(request.serial)

    return RemoteDeviceRemoveResponse(
        success=success,
        message=message,
        error=None if success else "remove_failed",
    )
