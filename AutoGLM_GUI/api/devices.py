"""Device discovery routes."""

from fastapi import APIRouter

from AutoGLM_GUI.schemas import (
    ConnectDeviceRequest,
    ConnectDeviceResponse,
    DeviceListResponse,
    DisconnectDeviceRequest,
    DisconnectDeviceResponse,
    EnableTcpipRequest,
    EnableTcpipResponse,
    GetDeviceIpRequest,
    GetDeviceIpResponse,
)
from AutoGLM_GUI.state import agents

router = APIRouter()


@router.get("/api/devices", response_model=DeviceListResponse)
def list_devices() -> DeviceListResponse:
    """列出所有 ADB 设备。"""
    from phone_agent.adb import list_devices as adb_list

    adb_devices = adb_list()

    return DeviceListResponse(
        devices=[
            {
                "id": d.device_id,
                "model": d.model or "Unknown",
                "status": d.status,
                "connection_type": d.connection_type.value,
                "is_initialized": d.device_id in agents,
            }
            for d in adb_devices
        ]
    )


@router.post("/api/devices/connect", response_model=ConnectDeviceResponse)
def connect_device(request: ConnectDeviceRequest) -> ConnectDeviceResponse:
    """通过 WiFi 连接到远程 ADB 设备。"""
    from phone_agent.adb import ADBConnection

    conn = ADBConnection()
    success, message = conn.connect(request.address, request.timeout)

    return ConnectDeviceResponse(success=success, message=message)


@router.post("/api/devices/disconnect", response_model=DisconnectDeviceResponse)
def disconnect_device(request: DisconnectDeviceRequest) -> DisconnectDeviceResponse:
    """断开 WiFi ADB 设备连接。"""
    from phone_agent.adb import ADBConnection

    conn = ADBConnection()
    success, message = conn.disconnect(request.address)

    return DisconnectDeviceResponse(success=success, message=message)


@router.post("/api/devices/enable-tcpip", response_model=EnableTcpipResponse)
def enable_tcpip(request: EnableTcpipRequest) -> EnableTcpipResponse:
    """在 USB 连接的设备上启用 TCP/IP 模式（WiFi ADB）。"""
    from phone_agent.adb import ADBConnection

    conn = ADBConnection()

    # 启用 TCP/IP
    success, message = conn.enable_tcpip(request.port, request.device_id)

    if not success:
        return EnableTcpipResponse(success=False, message=message, device_ip=None)

    # 尝试获取设备 IP
    device_ip = conn.get_device_ip(request.device_id)

    if device_ip:
        return EnableTcpipResponse(
            success=True,
            message=f"{message}。设备 IP: {device_ip}。现在可以拔掉 USB 线，使用 WiFi 连接。",
            device_ip=device_ip,
        )
    else:
        return EnableTcpipResponse(
            success=True,
            message=f"{message}。无法自动获取设备 IP，请手动查看设备网络设置后使用 WiFi 连接。",
            device_ip=None,
        )


@router.post("/api/devices/ip", response_model=GetDeviceIpResponse)
def get_device_ip(request: GetDeviceIpRequest) -> GetDeviceIpResponse:
    """获取设备的 IP 地址。"""
    from phone_agent.adb import ADBConnection

    conn = ADBConnection()
    device_ip = conn.get_device_ip(request.device_id)

    if device_ip:
        return GetDeviceIpResponse(success=True, ip=device_ip, message=None)
    else:
        return GetDeviceIpResponse(
            success=False,
            ip=None,
            message="无法获取设备 IP 地址。请确保设备已连接并启用了 WiFi。",
        )
