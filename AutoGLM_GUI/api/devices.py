"""Device discovery routes."""

from fastapi import APIRouter

from AutoGLM_GUI.adb_plus import get_wifi_ip

from AutoGLM_GUI.schemas import (
    DeviceListResponse,
    WiFiConnectRequest,
    WiFiConnectResponse,
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


@router.post("/api/devices/connect_wifi", response_model=WiFiConnectResponse)
def connect_wifi(request: WiFiConnectRequest) -> WiFiConnectResponse:
    """从 USB 启用 TCP/IP 并连接到 WiFi。"""
    from phone_agent.adb import ADBConnection, ConnectionType

    conn = ADBConnection()

    # 优先使用传入的 device_id，否则取第一个在线设备
    device_info = conn.get_device_info(request.device_id)
    if not device_info:
        return WiFiConnectResponse(
            success=False,
            message="No connected device found",
            error="device_not_found",
        )

    # 已经是 WiFi 连接则直接返回
    if device_info.connection_type == ConnectionType.REMOTE:
        address = device_info.device_id
        return WiFiConnectResponse(
            success=True,
            message="Already connected over WiFi",
            device_id=address,
            address=address,
        )

    # 1) 启用 tcpip
    ok, msg = conn.enable_tcpip(port=request.port, device_id=device_info.device_id)
    if not ok:
        return WiFiConnectResponse(
            success=False, message=msg or "Failed to enable tcpip", error="tcpip"
        )

    # 2) 读取设备 IP：先用本地 adb_plus 的 WiFi 优先逻辑，失败再回退上游接口
    ip = get_wifi_ip(conn.adb_path, device_info.device_id) or conn.get_device_ip(
        device_info.device_id
    )
    if not ip:
        return WiFiConnectResponse(
            success=False, message="Failed to get device IP", error="ip"
        )

    address = f"{ip}:{request.port}"

    # 3) 连接 WiFi
    ok, msg = conn.connect(address)
    if not ok:
        return WiFiConnectResponse(
            success=False,
            message=msg or "Failed to connect over WiFi",
            error="connect",
        )

    return WiFiConnectResponse(
        success=True,
        message="Switched to WiFi successfully",
        device_id=address,
        address=address,
    )
