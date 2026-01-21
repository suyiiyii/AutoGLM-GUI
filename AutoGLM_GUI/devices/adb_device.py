"""ADB Device implementation of DeviceProtocol."""

from AutoGLM_GUI import adb
from AutoGLM_GUI.adb import ADBConnection
from AutoGLM_GUI.device_protocol import (
    DeviceInfo,
    DeviceManagerProtocol,
    DeviceProtocol,
    Screenshot,
)


class ADBDevice(DeviceProtocol):
    """
    ADB device implementation using local subprocess calls.

    Wraps the existing phone_agent.adb module to provide a clean
    DeviceProtocol interface.

    Example:
        >>> device = ADBDevice("emulator-5554")
        >>> screenshot = device.get_screenshot()
        >>> device.tap(100, 200)
        >>> device.swipe(100, 200, 300, 400)
    """

    def __init__(self, device_id: str):
        """
        Initialize ADB device.

        Args:
            device_id: ADB device ID (e.g., "emulator-5554", "192.168.1.100:5555").
        """
        self._device_id = device_id

    @property
    def device_id(self) -> str:
        """Unique device identifier."""
        return self._device_id

    # === Screenshot ===
    def get_screenshot(self, timeout: int = 10) -> Screenshot:
        """Capture current screen."""
        result = adb.get_screenshot(self._device_id, timeout)
        return Screenshot(
            base64_data=result.base64_data,
            width=result.width,
            height=result.height,
            is_sensitive=result.is_sensitive,
        )

    # === Input Operations ===
    def tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Tap at specified coordinates."""
        adb.tap(x, y, self._device_id, delay)

    def double_tap(self, x: int, y: int, delay: float | None = None) -> None:
        """Double tap at specified coordinates."""
        adb.double_tap(x, y, self._device_id, delay)

    def long_press(
        self, x: int, y: int, duration_ms: int = 3000, delay: float | None = None
    ) -> None:
        """Long press at specified coordinates."""
        adb.long_press(x, y, duration_ms, self._device_id, delay)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        delay: float | None = None,
    ) -> None:
        """Swipe from start to end coordinates."""
        adb.swipe(start_x, start_y, end_x, end_y, duration_ms, self._device_id, delay)

    def type_text(self, text: str) -> None:
        """Type text into the currently focused input field."""
        adb.type_text(text, self._device_id)

    def clear_text(self) -> None:
        """Clear text in the currently focused input field."""
        adb.clear_text(self._device_id)

    # === Navigation ===
    def back(self, delay: float | None = None) -> None:
        """Press the back button."""
        adb.back(self._device_id, delay)

    def home(self, delay: float | None = None) -> None:
        """Press the home button."""
        adb.home(self._device_id, delay)

    def launch_app(self, app_name: str, delay: float | None = None) -> bool:
        """Launch an app by name."""
        return adb.launch_app(app_name, self._device_id, delay)

    # === State Query ===
    def get_current_app(self) -> str:
        """Get the currently focused app name."""
        return adb.get_current_app(self._device_id)

    # === Keyboard Management ===
    def detect_and_set_adb_keyboard(self) -> str:
        """Detect current keyboard and switch to ADB Keyboard if needed."""
        return adb.detect_and_set_adb_keyboard(self._device_id)

    def restore_keyboard(self, ime: str) -> None:
        """Restore the original keyboard IME."""
        adb.restore_keyboard(ime, self._device_id)


# Verify ADBDevice implements DeviceProtocol
assert isinstance(ADBDevice("test"), DeviceProtocol)


class ADBDeviceManager(DeviceManagerProtocol):
    """
    ADB device manager implementation.

    Manages multiple ADB devices and provides DeviceProtocol instances.

    Example:
        >>> manager = ADBDeviceManager()
        >>> devices = manager.list_devices()
        >>> device = manager.get_device("emulator-5554")
        >>> device.tap(100, 200)
    """

    def __init__(self, adb_path: str = "adb"):
        """
        Initialize the device manager.

        Args:
            adb_path: Path to ADB executable.
        """
        self._connection = ADBConnection(adb_path)
        self._devices: dict[str, ADBDevice] = {}

    def list_devices(self) -> list[DeviceInfo]:
        """List all available devices."""
        adb_devices = self._connection.list_devices()
        result = []

        for dev in adb_devices:
            result.append(
                DeviceInfo(
                    device_id=dev.device_id,
                    status="online" if dev.status == "device" else dev.status,
                    model=dev.model,
                    platform="android",
                    connection_type=dev.connection_type.value,
                )
            )

        return result

    def get_device(self, device_id: str) -> ADBDevice:
        """
        Get a device instance by ID.

        Args:
            device_id: The device ID.

        Returns:
            ADBDevice instance.

        Raises:
            KeyError: If device not found or offline.
        """
        # Check if device exists and is online
        devices = self.list_devices()
        device_info = next((d for d in devices if d.device_id == device_id), None)

        if device_info is None:
            raise KeyError(f"Device '{device_id}' not found")
        if device_info.status != "online":
            raise KeyError(f"Device '{device_id}' is {device_info.status}")

        # Cache and return device instance
        if device_id not in self._devices:
            self._devices[device_id] = ADBDevice(device_id)

        return self._devices[device_id]

    def connect(self, address: str, timeout: int = 10) -> tuple[bool, str]:
        """Connect to a remote device."""
        return self._connection.connect(address, timeout)

    def disconnect(self, device_id: str) -> tuple[bool, str]:
        """Disconnect from a device."""
        # Remove from cache
        self._devices.pop(device_id, None)
        return self._connection.disconnect(device_id)


# Verify ADBDeviceManager implements DeviceManagerProtocol
assert isinstance(ADBDeviceManager(), DeviceManagerProtocol)
