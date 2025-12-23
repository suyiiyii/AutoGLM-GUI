"""ADB Keyboard Auto-Installation and Enablement Tool.

This module provides automatic installation, configuration, and enabling of ADB Keyboard,
without requiring users to manually download and install APK.
"""

import asyncio
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import run_cmd_silently

ADB_KEYBOARD_PACKAGE = "com.android.adbkeyboard"
ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
ADB_KEYBOARD_APK_URL = (
    "https://github.com/senzhk/ADBKeyBoard/raw/master/ADBKeyboard.apk"
)
ADB_KEYBOARD_APK_FILENAME = "ADBKeyboard.apk"

# APK file in user cache directory (fallback)
USER_CACHE_APK_PATH = Path.home() / ".cache" / "autoglm" / ADB_KEYBOARD_APK_FILENAME


class ADBKeyboardInstaller:
    """ADB Keyboard Auto-Installer."""

    def __init__(self, device_id: Optional[str] = None):
        """
        Initialize the installer.

        Args:
            device_id: Optional ADB device ID for multi-device scenarios.
        """
        self.device_id = device_id
        self.adb_prefix = ["adb"]
        if device_id:
            self.adb_prefix.extend(["-s", device_id])

        logger.debug(
            f"Initialized ADBKeyboardInstaller for device: {device_id or 'default'}"
        )

    def is_installed(self) -> bool:
        """
        Check if ADB Keyboard is installed (via package name).

        Returns:
            bool: True if installed, False otherwise.
        """
        try:
            logger.debug(
                f"Checking if ADB Keyboard is installed on device {self.device_id or 'default'}"
            )
            result = asyncio.run(
                run_cmd_silently(self.adb_prefix + ["shell", "pm", "list", "packages"])
            )
            package_list = result.stdout.strip()
            installed = ADB_KEYBOARD_PACKAGE in package_list
            logger.debug(f"ADB Keyboard installed: {installed}")
            return installed
        except Exception as e:
            logger.error(f"Error checking keyboard installation status: {e}")
            return False

    def is_enabled(self) -> bool:
        """
        Check if ADB Keyboard is enabled (usable).

        Determined by checking the list of enabled input methods.

        Returns:
            bool: True if enabled, False otherwise.
        """
        try:
            logger.debug(
                f"Checking if ADB Keyboard is enabled on device {self.device_id or 'default'}"
            )
            # Use ime list -s to check only enabled input methods
            result = asyncio.run(
                run_cmd_silently(self.adb_prefix + ["shell", "ime", "list", "-s"])
            )
            ime_list_enabled = result.stdout.strip()
            enabled = ADB_KEYBOARD_IME in ime_list_enabled
            logger.debug(f"ADB Keyboard enabled: {enabled}")
            return enabled
        except Exception as e:
            logger.error(f"Error checking keyboard enable status: {e}")
            return False

    def get_apk_path(self) -> Optional[Path]:
        """
        Get APK file path.

        Prioritizes returning the APK file within the project (bundled in wheel),
        falls back to user cache if not exists.

        Returns:
            Optional[Path]: APK file path, or None if neither exists.
        """
        # Priority 1: Try bundled resource (packaged in wheel)
        try:
            from importlib.resources import files

            logger.debug("Searching for bundled APK in wheel package")
            resource = files("AutoGLM_GUI").joinpath(
                "resources/apks", ADB_KEYBOARD_APK_FILENAME
            )
            # Convert to Path
            if hasattr(resource, "read_bytes"):
                # For Python 3.9+, use as_file() context manager
                from importlib.resources import as_file

                with as_file(resource) as path:
                    if path.exists():
                        logger.info(f"Found bundled APK: {path}")
                        return path
            elif hasattr(resource, "_path"):
                # Fallback for older importlib.resources
                path = Path(str(resource))
                if path.exists():
                    logger.info(f"Found bundled APK: {path}")
                    return path
        except Exception as e:
            logger.debug(f"Bundled APK not found: {e}")

        # Priority 2: Try user cache directory
        if USER_CACHE_APK_PATH.exists():
            logger.info(f"Found cached APK: {USER_CACHE_APK_PATH}")
            return USER_CACHE_APK_PATH

        logger.warning("APK file not found in bundled resources or cache")
        return None

    def download_apk(self, force: bool = False) -> bool:
        """
        Get or download ADB Keyboard APK.

        Prioritizes using the APK file within the project, downloads from GitHub if not exists.

        Args:
            force: Whether to force re-download even if file already exists.

        Returns:
            bool: True if APK is successfully obtained, False otherwise.
        """
        # Check if APK already exists
        existing_apk = self.get_apk_path()
        if existing_apk and not force:
            logger.debug(f"APK already exists at {existing_apk}, skipping download")
            return True

        # Download from GitHub
        logger.info(f"Downloading ADB Keyboard APK from {ADB_KEYBOARD_APK_URL}")

        # Ensure cache directory exists
        USER_CACHE_APK_PATH.parent.mkdir(parents=True, exist_ok=True)

        try:
            urllib.request.urlretrieve(ADB_KEYBOARD_APK_URL, USER_CACHE_APK_PATH)

            if USER_CACHE_APK_PATH.exists() and USER_CACHE_APK_PATH.stat().st_size > 0:
                logger.info(f"APK downloaded successfully to {USER_CACHE_APK_PATH}")
                return True
            else:
                logger.error("Downloaded APK is empty or invalid")
                return False

        except Exception as e:
            logger.error(f"Failed to download APK: {e}")
            # Clean up incomplete file
            if USER_CACHE_APK_PATH.exists():
                USER_CACHE_APK_PATH.unlink()
            return False

    def install(self) -> Tuple[bool, str]:
        """
        Install ADB Keyboard APK.

        Returns:
            Tuple[bool, str]: (success, message)
        """
        apk_path = self.get_apk_path()
        if not apk_path or not apk_path.exists():
            error_msg = "APK file not found. Please download first."
            logger.error(error_msg)
            return False, error_msg

        try:
            logger.info(f"Installing ADB Keyboard from {apk_path}")
            result = asyncio.run(
                run_cmd_silently(self.adb_prefix + ["install", "-r", str(apk_path)])
            )

            if "Success" in result.stdout or result.returncode == 0:
                success_msg = "ADB Keyboard installed successfully"
                logger.info(success_msg)
                return True, success_msg
            else:
                error_msg = f"Installation failed: {result.stdout} {result.stderr}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Installation error: {e}"
            logger.exception("Unexpected error during installation")
            return False, error_msg

    def enable(self) -> Tuple[bool, str]:
        """
        Enable ADB Keyboard (enable only, do not modify default input method).

        Note: This only enables ADB Keyboard, does not set it as default input method.
        In actual usage, Phone Agent will temporarily switch via detect_and_set_adb_keyboard().

        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            logger.info("Enabling ADB Keyboard IME")
            # Enable keyboard
            result = asyncio.run(
                run_cmd_silently(
                    self.adb_prefix + ["shell", "ime", "enable", ADB_KEYBOARD_IME]
                )
            )

            if result.returncode == 0:
                success_msg = "ADB Keyboard enabled successfully"
                logger.info(success_msg)
                return True, success_msg
            else:
                # Some devices return non-zero but still succeed, verify with is_enabled()
                if self.is_enabled():
                    success_msg = "ADB Keyboard enabled (verified)"
                    logger.info(success_msg)
                    return True, success_msg
                else:
                    error_msg = f"Enable failed: {result.stdout} {result.stderr}"
                    logger.warning(error_msg)
                    return False, error_msg

        except Exception as e:
            error_msg = f"Enable error: {e}"
            logger.exception("Unexpected error during enable")
            return False, error_msg

    def auto_setup(self) -> Tuple[bool, str]:
        """
        Automatically complete installation and enablement process.

        Intelligent handling:
        1. Installed and enabled - skip, return True
        2. Installed but not enabled - enable only, return result
        3. Not installed - install+enable, return result

        Note: This method does not interact with users, all user prompts should be handled by the caller.

        Returns:
            Tuple[bool, str]: (success, message)
        """
        logger.debug("Starting auto-setup for ADB Keyboard")

        # Check current status
        installed = self.is_installed()
        enabled = self.is_enabled()

        # Status 1: Installed and enabled
        if installed and enabled:
            msg = "ADB Keyboard is ready (already installed and enabled)"
            logger.info(msg)
            return True, msg

        # Status 2: Installed but not enabled
        if installed and not enabled:
            logger.info("ADB Keyboard is installed but not enabled, enabling now")
            return self.enable()

        # Status 3: Not installed
        if not installed:
            logger.info("ADB Keyboard is not installed, starting installation")

            # Step 1: Download APK (if not already available)
            if not self.download_apk():
                error_msg = "Failed to download APK"
                logger.error(error_msg)
                return False, error_msg

            # Step 2: Install
            success, message = self.install()
            if not success:
                logger.error(f"Installation failed: {message}")
                return False, message

            # Step 3: Enable
            success, message = self.enable()
            if not success:
                logger.error(f"Enable failed: {message}")
                return False, message

            # Verify final status
            if self.is_installed() and self.is_enabled():
                success_msg = "ADB Keyboard setup completed successfully"
                logger.info(success_msg)
                return True, success_msg
            else:
                error_msg = "Setup completed but verification failed"
                logger.warning(error_msg)
                return False, error_msg

        # Default return failure
        error_msg = "Unknown status, setup failed"
        logger.error(error_msg)
        return False, error_msg

    def get_status(self) -> dict:
        """
        Get detailed status of ADB Keyboard.

        Returns:
            dict: Dictionary containing installation and enablement status.
        """
        apk_path = self.get_apk_path()
        installed = self.is_installed()
        enabled = self.is_enabled()

        # Determine current status
        if installed and enabled:
            status = "ready"  # Ready
        elif installed and not enabled:
            status = "installed_but_disabled"  # Installed but not enabled
        elif not installed:
            status = "not_installed"  # Not installed
        else:
            status = "unknown"  # Unknown

        return {
            "installed": installed,
            "enabled": enabled,
            "status": status,
            "status_text": {
                "ready": "Installed and enabled",
                "installed_but_disabled": "Installed but not enabled",
                "not_installed": "Not installed",
                "unknown": "Unknown status",
            }.get(status, "Unknown"),
            "apk_exists": apk_path is not None and apk_path.exists(),
            "apk_path": str(apk_path) if apk_path else "N/A",
            "cache_apk_exists": USER_CACHE_APK_PATH.exists(),
            "cache_apk_path": str(USER_CACHE_APK_PATH),
        }


def auto_setup_adb_keyboard(device_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Convenience function: One-click auto-install and enable ADB Keyboard.

    Args:
        device_id: Optional device ID.

    Returns:
        Tuple[bool, str]: (success, message)
    """
    installer = ADBKeyboardInstaller(device_id)
    return installer.auto_setup()


def check_and_suggest_installation() -> bool:
    """
    Check if ADB Keyboard needs installation.

    Note: This function does not interact with users, only returns boolean value.
    All user prompts should be handled by the caller.

    Returns:
        bool: True if not installed, False otherwise.
    """
    installer = ADBKeyboardInstaller()
    return not installer.is_installed()
