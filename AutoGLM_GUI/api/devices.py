"""Device discovery routes."""

from fastapi import APIRouter

from AutoGLM_GUI.adb_plus import get_wifi_ip, get_device_serial, pair_device

from AutoGLM_GUI.schemas import (
    DeviceListResponse,
    WiFiConnectRequest,
    WiFiConnectResponse,
    WiFiDisconnectRequest,
    WiFiDisconnectResponse,
    WiFiManualConnectRequest,
    WiFiManualConnectResponse,
    WiFiPairRequest,
    WiFiPairResponse,
    MdnsDiscoverResponse,
    MdnsDeviceResponse,
)
from AutoGLM_GUI.state import agents

router = APIRouter()


@router.get("/api/devices", response_model=DeviceListResponse)
def list_devices() -> DeviceListResponse:
    """列出所有 ADB 设备。"""
    from phone_agent.adb import list_devices as adb_list, ADBConnection

    adb_devices = adb_list()
    conn = ADBConnection()

    devices_with_serial = []
    for d in adb_devices:
        # 使用 adb_plus 的 get_device_serial 获取真实序列号
        serial = get_device_serial(d.device_id, conn.adb_path)

        devices_with_serial.append(
            {
                "id": d.device_id,
                "model": d.model or "Unknown",
                "status": d.status,
                "connection_type": d.connection_type.value,
                "is_initialized": d.device_id in agents,
                "serial": serial,  # 真实序列号
            }
        )

    return DeviceListResponse(devices=devices_with_serial)


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


@router.post("/api/devices/disconnect_wifi", response_model=WiFiDisconnectResponse)
def disconnect_wifi(request: WiFiDisconnectRequest) -> WiFiDisconnectResponse:
    """断开 WiFi 连接。"""
    from phone_agent.adb import ADBConnection

    conn = ADBConnection()
    ok, msg = conn.disconnect(request.device_id)

    return WiFiDisconnectResponse(
        success=ok,
        message=msg,
        error=None if ok else "disconnect_failed",
    )


@router.post(
    "/api/devices/connect_wifi_manual", response_model=WiFiManualConnectResponse
)
def connect_wifi_manual(
    request: WiFiManualConnectRequest,
) -> WiFiManualConnectResponse:
    """手动连接到 WiFi 设备 (直接连接,无需 USB)."""
    import re

    from phone_agent.adb import ADBConnection

    # IP 格式验证
    ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    if not re.match(ip_pattern, request.ip):
        return WiFiManualConnectResponse(
            success=False,
            message="Invalid IP address format",
            error="invalid_ip",
        )

    # 端口范围验证
    if not (1 <= request.port <= 65535):
        return WiFiManualConnectResponse(
            success=False,
            message="Port must be between 1 and 65535",
            error="invalid_port",
        )

    conn = ADBConnection()
    address = f"{request.ip}:{request.port}"

    # 直接连接
    ok, msg = conn.connect(address)
    if not ok:
        return WiFiManualConnectResponse(
            success=False,
            message=msg or f"Failed to connect to {address}",
            error="connect_failed",
        )

    return WiFiManualConnectResponse(
        success=True,
        message=f"Successfully connected to {address}",
        device_id=address,
    )


@router.post("/api/devices/pair_wifi", response_model=WiFiPairResponse)
def pair_wifi(request: WiFiPairRequest) -> WiFiPairResponse:
    """使用无线调试配对并连接到 WiFi 设备 (Android 11+)."""
    import re

    from phone_agent.adb import ADBConnection

    # IP 格式验证
    ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    if not re.match(ip_pattern, request.ip):
        return WiFiPairResponse(
            success=False,
            message="Invalid IP address format",
            error="invalid_ip",
        )

    # 配对端口验证
    if not (1 <= request.pairing_port <= 65535):
        return WiFiPairResponse(
            success=False,
            message="Pairing port must be between 1 and 65535",
            error="invalid_port",
        )

    # 连接端口验证
    if not (1 <= request.connection_port <= 65535):
        return WiFiPairResponse(
            success=False,
            message="Connection port must be between 1 and 65535",
            error="invalid_port",
        )

    # 配对码验证 (6 位数字)
    if not request.pairing_code.isdigit() or len(request.pairing_code) != 6:
        return WiFiPairResponse(
            success=False,
            message="Pairing code must be 6 digits",
            error="invalid_pairing_code",
        )

    conn = ADBConnection()

    # 步骤 1: 配对设备
    ok, msg = pair_device(
        ip=request.ip,
        port=request.pairing_port,
        pairing_code=request.pairing_code,
        adb_path=conn.adb_path,
    )

    if not ok:
        return WiFiPairResponse(
            success=False,
            message=msg,
            error="pair_failed",
        )

    # 步骤 2: 使用标准 ADB 端口连接到设备
    connection_address = f"{request.ip}:{request.connection_port}"
    ok, connect_msg = conn.connect(connection_address)

    if not ok:
        return WiFiPairResponse(
            success=False,
            message=f"Paired successfully but connection failed: {connect_msg}",
            error="connect_failed",
        )

    return WiFiPairResponse(
        success=True,
        message=f"Successfully paired and connected to {connection_address}",
        device_id=connection_address,
    )


@router.get("/api/devices/discover_mdns", response_model=MdnsDiscoverResponse)
def discover_mdns() -> MdnsDiscoverResponse:
    """Discover wireless ADB devices via mDNS."""
    from phone_agent.adb import ADBConnection
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
