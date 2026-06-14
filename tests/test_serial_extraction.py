"""Unit tests for mDNS serial extraction."""

import subprocess

import pytest

import AutoGLM_GUI.adb_plus.serial as serial_module
from AutoGLM_GUI.adb_plus.serial import extract_serial_from_mdns, get_device_serial


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["adb"], returncode=returncode, stdout=stdout
    )


class TestMdnsSerialExtraction:
    """Test mDNS serial number extraction."""

    def test_extract_from_tls_connect_service(self):
        """Test extraction from _adb-tls-connect service."""
        device_id = "adb-243baa09b7-cbCO6P._adb-tls-connect._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "243baa09b7"

    def test_extract_from_simple_service(self):
        """Test extraction from simple _adb service."""
        device_id = "adb-243baa09b7._adb._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "243baa09b7"

    def test_extract_from_local_hostname(self):
        """Test extraction from .local hostname."""
        device_id = "adb-ABC123DEF.local"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "ABC123DEF"

    def test_extract_with_suffix(self):
        """Test extraction with complex suffix."""
        device_id = "adb-1a2b3c4d-XyZ123._adb-tls-connect._tcp.local."
        serial = extract_serial_from_mdns(device_id)
        assert serial == "1a2b3c4d"

    def test_non_mdns_device_returns_none(self):
        """Test that non-mDNS devices return None."""
        assert extract_serial_from_mdns("192.168.1.100:5555") is None
        assert extract_serial_from_mdns("emulator-5554") is None
        assert extract_serial_from_mdns("FA12B3C4D5E6") is None

    def test_invalid_format_returns_none(self):
        """Test invalid mDNS formats return None."""
        # No serial
        assert extract_serial_from_mdns("adb-._adb._tcp") is None
        # Too short (less than 6 chars)
        assert extract_serial_from_mdns("adb-12._adb._tcp") is None
        assert extract_serial_from_mdns("adb-12345._adb._tcp") is None

    def test_uppercase_serial(self):
        """Test case handling for hex serials."""
        device_id = "adb-AbC123DeF._adb._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "AbC123DeF"

    def test_lowercase_serial(self):
        """Test lowercase hex serial."""
        device_id = "adb-abcdef123._adb-tls-connect._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "abcdef123"

    def test_mixed_case_serial(self):
        """Test mixed case hex serial."""
        device_id = "adb-1A2b3C4d5E._adb._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "1A2b3C4d5E"

    def test_tls_pairing_service(self):
        """Test extraction from _adb-tls-pairing service."""
        device_id = "adb-FEDCBA98-suffix._adb-tls-pairing._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "FEDCBA98"

    def test_minimum_length_serial(self):
        """Test serial with minimum valid length (6 chars)."""
        device_id = "adb-123456._adb._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "123456"

    def test_long_serial(self):
        """Test serial with longer length."""
        device_id = "adb-123456789ABCDEF0._adb-tls-connect._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "123456789ABCDEF0"

    def test_non_alphanumeric_in_suffix(self):
        """Test that non-alphanumeric characters in suffix don't affect extraction."""
        device_id = "adb-ABC123-suffix_with-dashes._adb._tcp"
        serial = extract_serial_from_mdns(device_id)
        assert serial == "ABC123"

    def test_empty_string(self):
        """Test empty string returns None."""
        assert extract_serial_from_mdns("") is None

    def test_only_adb_prefix(self):
        """Test string with only 'adb-' prefix returns None."""
        assert extract_serial_from_mdns("adb-") is None
        assert extract_serial_from_mdns("adb-._adb._tcp") is None

    def test_multiple_adb_patterns(self):
        """Test that first valid serial is extracted."""
        # Edge case: multiple "adb-" patterns (shouldn't happen in practice)
        device_id = "adb-111111-adb-222222._adb._tcp"
        serial = extract_serial_from_mdns(device_id)
        # Should extract first valid serial
        assert serial == "111111"


class TestGetDeviceSerialIntegration:
    """Test get_device_serial() with mDNS extraction integration."""

    def test_mdns_device_uses_extraction(self):
        """Test that mDNS devices use extraction instead of getprop."""
        # This should use extraction (fast path)
        device_id = "adb-TESTSER._adb-tls-connect._tcp"
        serial = get_device_serial(device_id)
        # Should return extracted serial without calling adb
        assert serial == "TESTSER"

    def test_usb_device_id_uses_fallback(self):
        """Test that non-mDNS USB device IDs use device_id as fallback."""
        # USB device ID (no extraction, will try getprop which will fail in test env)
        # Now uses device_id as fallback for emulators/restricted devices
        device_id = "ABC123DEF456"
        serial = get_device_serial(device_id)
        # Without real adb, this should return device_id as fallback
        assert serial == device_id

    def test_wifi_ip_uses_fallback(self):
        """Test that WiFi IP addresses use device_id as fallback when getprop fails."""
        device_id = "192.168.1.100:5555"
        serial = get_device_serial(device_id)
        # Without real adb, this should return device_id as fallback
        assert serial == device_id

    def test_invalid_mdns_uses_fallback(self):
        """Test that invalid mDNS formats use device_id as fallback."""
        # Invalid mDNS format (too short serial)
        device_id = "adb-12._adb._tcp"
        serial = get_device_serial(device_id)
        # Extraction fails, getprop attempted (fails in test env), uses fallback
        assert serial == device_id

    def test_getprop_returns_first_valid_serial(self, monkeypatch: pytest.MonkeyPatch):
        """Test getprop fallback skips empty/error values and returns a valid serial."""
        results = iter(
            [
                _completed(""),
                _completed("unknown"),
                _completed("SERIAL123"),
            ]
        )
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return next(results)

        monkeypatch.setattr(serial_module, "run_cmd_silently_sync", fake_run)

        assert get_device_serial("usb-device", adb_path="adbx") == "SERIAL123"
        assert [call[-1] for call in calls] == [
            "ro.serialno",
            "ro.boot.serialno",
            "ro.product.serial",
        ]

    def test_getprop_exceptions_fall_through_to_next_prop(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Test getprop exceptions are ignored before trying the next property."""
        calls = 0

        def fake_run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("adb failed")
            return _completed("SERIAL456")

        monkeypatch.setattr(serial_module, "run_cmd_silently_sync", fake_run)

        assert get_device_serial("usb-device", adb_path="adbx") == "SERIAL456"
        assert calls == 2


@pytest.mark.anyio
async def test_get_device_serial_async_uses_mdns_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_if_called(
        cmd: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError("ADB should not be called for valid mDNS names")

    monkeypatch.setattr(serial_module, "run_cmd_silently", fail_if_called)

    assert (
        await serial_module.get_device_serial_async("adb-ASYNC1._adb-tls-connect._tcp")
        == "ASYNC1"
    )


@pytest.mark.anyio
async def test_get_device_serial_async_returns_first_valid_getprop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter(
        [
            _completed("error: device offline"),
            _completed("unknown"),
            _completed("ASYNC123"),
        ]
    )
    calls: list[list[str]] = []

    async def fake_run(
        cmd: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return next(results)

    monkeypatch.setattr(serial_module, "run_cmd_silently", fake_run)

    assert (
        await serial_module.get_device_serial_async("wifi-device", adb_path="adbx")
        == "ASYNC123"
    )
    assert [call[-1] for call in calls] == [
        "ro.serialno",
        "ro.boot.serialno",
        "ro.product.serial",
    ]


@pytest.mark.anyio
async def test_get_device_serial_async_exceptions_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_run(
        cmd: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("adb failed")

    monkeypatch.setattr(serial_module, "run_cmd_silently", broken_run)

    assert await serial_module.get_device_serial_async("wifi-device") == "wifi-device"
