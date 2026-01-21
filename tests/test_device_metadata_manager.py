"""Unit tests for DeviceMetadataManager."""

import json
import tempfile
import pytest
from pathlib import Path

from AutoGLM_GUI.device_metadata_manager import (
    DeviceMetadataManager,
    DISPLAY_NAME_MAX_LENGTH,
)


class TestDeviceMetadataManager:
    """Test DeviceMetadataManager singleton functionality."""

    @pytest.fixture
    def manager(self):
        """Create a fresh DeviceMetadataManager instance for each test."""
        # Reset singleton to ensure clean state
        DeviceMetadataManager._instance = None

        with tempfile.TemporaryDirectory() as temp_dir:
            # Set custom metadata path for testing
            manager = DeviceMetadataManager.get_instance(storage_dir=Path(temp_dir))
            yield manager

            # Cleanup
            DeviceMetadataManager._instance = None

    def test_singleton_returns_same_instance(self):
        """Test that get_instance returns the same instance."""
        DeviceMetadataManager._instance = None
        instance1 = DeviceMetadataManager.get_instance()
        instance2 = DeviceMetadataManager.get_instance()
        assert instance1 is instance2
        DeviceMetadataManager._instance = None

    def test_get_display_name_returns_none_for_unknown_device(self, manager):
        """Test getting display name for unknown device returns None."""
        result = manager.get_display_name("unknown_serial_123")
        assert result is None

    def test_set_and_get_display_name(self, manager):
        """Test setting and retrieving display name."""
        serial = "test_device_1"
        name = "My Test Device"

        manager.set_display_name(serial, name)
        result = manager.get_display_name(serial)

        assert result == name

    def test_set_empty_string_clears_name(self, manager):
        """Test setting empty string clears the display name."""
        serial = "test_device_2"
        name = "Original Name"

        # First set a name
        manager.set_display_name(serial, name)
        assert manager.get_display_name(serial) == name

        # Clear with empty string
        manager.set_display_name(serial, "")
        result = manager.get_display_name(serial)

        assert result is None

    def test_set_whitespace_only_clears_name(self, manager):
        """Test setting whitespace-only string clears the display name."""
        serial = "test_device_3"
        name = "Original Name"

        manager.set_display_name(serial, name)
        assert manager.get_display_name(serial) == name

        # Clear with whitespace
        manager.set_display_name(serial, "   \t\n  ")
        result = manager.get_display_name(serial)

        assert result is None

    def test_set_display_name_max_length(self, manager):
        """Test that display name length is enforced."""
        serial = "test_device_4"
        max_length_name = "X" * DISPLAY_NAME_MAX_LENGTH
        too_long_name = max_length_name + "X"

        # Max length should succeed
        manager.set_display_name(serial, max_length_name)
        assert manager.get_display_name(serial) == max_length_name

        # Too long should raise ValueError
        with pytest.raises(ValueError, match="too long"):
            manager.set_display_name(serial, too_long_name)

    def test_set_display_name_with_null_clears(self, manager):
        """Test that setting display_name to None clears the name."""
        serial = "test_device_5"
        name = "To Be Cleared"

        manager.set_display_name(serial, name)
        assert manager.get_display_name(serial) == name

        manager.set_display_name(serial, None)
        result = manager.get_display_name(serial)

        assert result is None

    def test_get_metadata_returns_dict_with_display_name(self, manager):
        """Test that get_metadata returns display_name when set."""
        serial = "test_device_6"
        name = "My Device"

        manager.set_display_name(serial, name)
        metadata = manager.get_metadata(serial)

        assert metadata is not None
        assert metadata.display_name == name
        assert hasattr(metadata, "last_updated")

    def test_get_metadata_returns_none_for_unknown_device(self, manager):
        """Test that get_metadata returns None for unknown device."""
        metadata = manager.get_metadata("unknown_serial_456")
        assert metadata is None

    def test_list_all_metadata(self, manager):
        """Test listing all metadata."""
        manager.set_display_name("dev1", "Device 1")
        manager.set_display_name("dev2", "Device 2")
        manager.set_display_name("dev3", "Device 3")

        all_metadata = manager.list_all_metadata()

        assert len(all_metadata) == 3
        assert all_metadata["dev1"].display_name == "Device 1"
        assert all_metadata["dev2"].display_name == "Device 2"
        assert all_metadata["dev3"].display_name == "Device 3"

    def test_corrupted_json_creates_backup(self, manager):
        """Test that corrupted JSON is backed up and recovered."""
        serial = "corruption_test_1"
        name = "Original Name"

        # Set valid data first
        manager.set_display_name(serial, name)

        # Corrupt file
        metadata_file = manager.metadata_file
        backup_file = metadata_file.with_suffix(".json.bak")

        with open(metadata_file, "w") as f:
            f.write("{invalid json content")

        # Reload manager from same storage (should handle corrupted file)
        DeviceMetadataManager._instance = None
        manager2 = DeviceMetadataManager.get_instance(storage_dir=manager.storage_dir)

        # Verify backup file was created
        assert backup_file.exists()

        # Metadata should be empty (corrupt file renamed to .bak)
        assert manager2.get_metadata(serial) is None

        DeviceMetadataManager._instance = None
        manager2 = DeviceMetadataManager.get_instance(storage_dir=manager.storage_dir)

        # Verify backup file was created
        assert backup_file.exists(), "Backup file should be created for corrupted JSON"

        # Metadata should be empty (corrupt file renamed to .bak)
        assert manager2.get_metadata(serial) is None

        DeviceMetadataManager._instance = None
        with tempfile.TemporaryDirectory() as temp_dir:
            manager2 = DeviceMetadataManager.get_instance(storage_dir=Path(temp_dir))

            # Verify backup file was created
            assert backup_file.exists(), (
                "Backup file should be created for corrupted JSON"
            )

            # Metadata should be empty (corrupt file renamed to .bak)
            assert manager2.get_metadata(serial) is None

            DeviceMetadataManager._instance = None

    def test_set_display_name_idempotent(self, manager):
        """Test that setting same value multiple times is idempotent."""
        serial = "idempotent_test_1"
        name = "Test Name"

        manager.set_display_name(serial, name)
        metadata1 = manager.get_metadata(serial)

        manager.set_display_name(serial, name)
        metadata2 = manager.get_metadata(serial)

        assert metadata1.last_updated == metadata2.last_updated

    def test_thread_safety_with_rlock(self, manager):
        """Test that multiple operations are thread-safe (basic check)."""
        import threading

        serial = "thread_safety_test"
        results = []

        def set_name():
            manager.set_display_name(serial, "Thread Test")

        def get_name():
            results.append(manager.get_display_name(serial))

        # Run multiple threads
        threads = [
            threading.Thread(target=set_name),
            threading.Thread(target=get_name),
            threading.Thread(target=set_name),
            threading.Thread(target=get_name),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=5)

        # All operations should complete without error
        assert len(results) > 0

    def test_list_all_metadata_returns_empty_dict_when_no_devices(self, manager):
        """Test that list_all_metadata returns empty dict initially."""
        DeviceMetadataManager._instance = None
        with tempfile.TemporaryDirectory() as temp_dir:
            fresh_manager = DeviceMetadataManager.get_instance(
                storage_dir=Path(temp_dir)
            )

            all_metadata = fresh_manager.list_all_metadata()

            assert all_metadata == {}

            DeviceMetadataManager._instance = None


class TestDeviceMetadataManagerValidation:
    """Test DeviceMetadataManager validation logic."""

    @pytest.fixture
    def manager(self):
        DeviceMetadataManager._instance = None
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DeviceMetadataManager.get_instance(storage_dir=Path(temp_dir))
            yield manager
            DeviceMetadataManager._instance = None

    def test_display_name_max_length_constant(self):
        """Test that DISPLAY_NAME_MAX_LENGTH is 100."""
        assert DISPLAY_NAME_MAX_LENGTH == 100

    def test_from_dict_valid_json(self, manager):
        """Test from_dict with valid JSON data."""
        serial = "from_dict_test"
        name = "Valid Name"

        manager.set_display_name(serial, name)
        metadata = manager.get_metadata(serial)

        assert metadata.display_name == name
        # JSON stores datetime as ISO string, parsed back as datetime object
        import datetime

        assert isinstance(metadata.last_updated, datetime.datetime)

    def test_from_dict_missing_last_updated_uses_current_time(self, manager):
        """Test that missing last_updated uses current time."""
        serial = "last_updated_test"

        # Manually create metadata without last_updated
        metadata_file = manager.metadata_file
        manual_data = {serial: {"display_name": "Manual Name"}}
        with open(metadata_file, "w") as f:
            json.dump(manual_data, f)

        # Reload manager from same storage
        DeviceMetadataManager._instance = None
        manager2 = DeviceMetadataManager.get_instance(storage_dir=manager.storage_dir)

        metadata = manager2.get_metadata(serial)
        assert metadata.display_name == "Manual Name"
        # JSON stores datetime as ISO string, parsed back as datetime object
        import datetime

        assert isinstance(metadata.last_updated, datetime.datetime)

        DeviceMetadataManager._instance = None
        with tempfile.TemporaryDirectory() as temp_dir:
            manager2 = DeviceMetadataManager.get_instance(storage_dir=Path(temp_dir))

            # Metadata should be empty (corrupt file renamed to .bak)
            assert manager2.get_metadata(serial) is None

            DeviceMetadataManager._instance = None

    def test_from_dict_invalid_json_structure_ignores_device(self, manager):
        """Test that malformed JSON file triggers backup and reset (fail-safe behavior)."""
        serial1 = "valid_device"
        serial2 = "invalid_device"

        # Set one valid device
        manager.set_display_name(serial1, "Valid Name")

        # Add malformed entry manually
        metadata_file = manager.metadata_file
        backup_file = metadata_file.with_suffix(".json.bak")

        with open(metadata_file, "r") as f:
            data = json.load(f)

        data[serial2] = "this is not a dict"

        with open(metadata_file, "w") as f:
            json.dump(data, f)

        # Reload manager from same storage
        DeviceMetadataManager._instance = None
        manager2 = DeviceMetadataManager.get_instance(storage_dir=manager.storage_dir)

        # After corruption, entire file is treated as bad (fail-safe behavior)
        # All devices return None, not just the malformed one
        assert manager2.get_display_name(serial1) is None
        assert manager2.get_display_name(serial2) is None

        # Verify backup was created
        assert backup_file.exists()

        DeviceMetadataManager._instance = None
