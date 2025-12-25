"""mDNS-based ADB device discovery."""

from __future__ import annotations

import re
from typing import Optional
from dataclasses import dataclass

from AutoGLM_GUI.platform_utils import run_cmd_silently_sync

__all__ = ["MdnsDevice", "discover_mdns_devices"]


@dataclass
class MdnsDevice:
    """Represents an mDNS-discovered ADB device."""

    name: str  # e.g., "adb-243a09b7-cbCO6P"
    ip: str  # e.g., "192.168.130.187"
    port: int  # e.g., 34553
    has_pairing: bool  # True if device also advertises pairing service
    service_type: str  # "_adb-tls-connect._tcp" or "_adb-tls-pairing._tcp"
    pairing_port: Optional[int] = None  # Pairing port if has_pairing is True


def _parse_mdns_line(line: str) -> tuple[str, str, str] | None:
    """
    Parse a single mDNS service line.

    Format: "name \t service_type \t ip:port"
    Example: "adb-243a09b7-cbCO6P\t_adb-tls-connect._tcp\t192.168.130.187:34553"

    Returns:
        Tuple of (name, service_type, address) or None if invalid
    """
    # Split by tab characters
    parts = line.split("\t")
    if len(parts) != 3:
        return None

    name = parts[0].strip()
    service_type = parts[1].strip()
    address = parts[2].strip()

    # Validate we have all parts
    if not (name and service_type and address):
        return None

    return name, service_type, address


def _parse_address(address: str) -> tuple[str, int] | None:
    """
    Parse IP:port from address string.

    Args:
        address: Format "ip:port", e.g., "192.168.130.187:34553"

    Returns:
        Tuple of (ip, port) or None if invalid or 0.0.0.0
    """
    # Match IP:port pattern
    match = re.match(r"^([\d.]+):(\d+)$", address)
    if not match:
        return None

    ip = match.group(1)
    port_str = match.group(2)

    # Skip 0.0.0.0 addresses (device not properly initialized)
    if ip == "0.0.0.0":
        return None

    # Validate IP format
    ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    if not re.match(ip_pattern, ip):
        return None

    # Validate IP octets
    octets = ip.split(".")
    if not all(0 <= int(octet) <= 255 for octet in octets):
        return None

    # Parse port
    try:
        port = int(port_str)
        if not (1 <= port <= 65535):
            return None
    except ValueError:
        return None

    return ip, port


def discover_mdns_devices(adb_path: str = "adb") -> list[MdnsDevice]:
    """
    Discover wireless ADB devices via mDNS.

    Args:
        adb_path: Path to adb executable

    Returns:
        List of discovered devices, consolidated by device name

    Example:
        >>> devices = discover_mdns_devices()
        >>> for dev in devices:
        ...     print(f"{dev.name} at {dev.ip}:{dev.port}")
        adb-243a09b7-cbCO6P at 192.168.130.187:34553
    """
    try:
        result = run_cmd_silently_sync([adb_path, "mdns", "services"], timeout=5)

        # Check for errors
        if result.returncode != 0:
            return []

        output = result.stdout
        if not output:
            return []

        # Parse devices by name (consolidate multiple service types)
        devices_dict: dict[str, dict] = {}

        for line in output.splitlines():
            # Skip header line
            if "List of discovered mdns services" in line:
                continue

            # Parse line
            parsed = _parse_mdns_line(line)
            if not parsed:
                continue

            name, service_type, address = parsed

            # Track pairing service separately (even if 0.0.0.0)
            is_pairing_service = "_adb-tls-pairing._tcp" in service_type
            is_connect_service = "_adb-tls-connect._tcp" in service_type

            if name not in devices_dict:
                devices_dict[name] = {
                    "name": name,
                    "ip": None,
                    "port": None,
                    "service_type": None,
                    "has_pairing": False,
                    "pairing_port": None,
                }

            # If this is a pairing service, mark it and save pairing port
            if is_pairing_service:
                devices_dict[name]["has_pairing"] = True
                # Extract pairing port directly from address string (even if IP is 0.0.0.0)
                if ":" in address:
                    try:
                        port_str = address.split(":")[-1]
                        pairing_port = int(port_str)
                        if 1 <= pairing_port <= 65535:
                            devices_dict[name]["pairing_port"] = pairing_port
                    except ValueError:
                        pass

            # Only use connect service for actual connection
            # Parse address for connect service
            addr_parsed = _parse_address(address)
            if is_connect_service and addr_parsed:
                ip, port = addr_parsed
                devices_dict[name]["ip"] = ip
                devices_dict[name]["port"] = port
                devices_dict[name]["service_type"] = service_type

        # Convert to MdnsDevice objects (filter out devices without valid address)
        devices = []
        for dev_data in devices_dict.values():
            if dev_data["ip"] and dev_data["port"]:
                devices.append(
                    MdnsDevice(
                        name=dev_data["name"],
                        ip=dev_data["ip"],
                        port=dev_data["port"],
                        has_pairing=dev_data["has_pairing"],
                        service_type=dev_data["service_type"],
                        pairing_port=dev_data["pairing_port"],
                    )
                )

        return devices

    except Exception:
        # Return empty list on any error (timeout, command not found, etc.)
        return []
