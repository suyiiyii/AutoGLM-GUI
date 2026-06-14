"""Contract tests for ADB Keyboard installer – is_enabled fallback logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from AutoGLM_GUI.adb_plus.keyboard_installer import (
    ADB_KEYBOARD_IME,
    ADB_KEYBOARD_PACKAGE,
    ADBKeyboardInstaller,
)

pytestmark = [pytest.mark.contract, pytest.mark.release_gate]


def _fake_result(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _make_installer(device_id: str | None = None) -> ADBKeyboardInstaller:
    return ADBKeyboardInstaller(device_id=device_id)


# ---------------------------------------------------------------------------
# is_enabled – settings-based primary check
# ---------------------------------------------------------------------------


class TestIsEnabledSettingsPrimary:
    """When `settings get secure enabled_input_methods` returns a valid value."""

    def test_enabled_via_settings(self) -> None:
        """ADB Keyboard package found in settings output → enabled."""
        settings_output = f"com.android.adbkeyboard/.AdbIME:{ADB_KEYBOARD_PACKAGE}"
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.return_value = _fake_result(stdout=settings_output)
            assert _make_installer().is_enabled() is True
            # Should only call settings, not fall back to ime list
            assert mock_run.call_count == 1
            call_args = mock_run.call_args[0][0]
            assert "settings" in call_args
            assert "enabled_input_methods" in call_args

    def test_disabled_via_settings(self) -> None:
        """Other IME packages present but not ADB Keyboard → disabled."""
        settings_output = "com.google.android.inputmethod.latin/.LatinIME:com.samsung.android.adaptiveemoji/.AdaptiveEmoji"
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.return_value = _fake_result(stdout=settings_output)
            assert _make_installer().is_enabled() is False
            assert mock_run.call_count == 1

    def test_settings_returns_null(self) -> None:
        """settings returns 'null' → fall back to ime list -s."""
        ime_list = f"{ADB_KEYBOARD_IME}\n"
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.side_effect = [
                _fake_result(stdout="null"),
                _fake_result(stdout=ime_list),
            ]
            assert _make_installer().is_enabled() is True
            assert mock_run.call_count == 2

    def test_settings_returns_empty(self) -> None:
        """settings returns empty string → fall back to ime list -s."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.side_effect = [
                _fake_result(stdout=""),
                _fake_result(stdout=f"{ADB_KEYBOARD_IME}\n"),
            ]
            assert _make_installer().is_enabled() is True
            assert mock_run.call_count == 2

    def test_settings_nonzero_exit(self) -> None:
        """settings returns non-zero exit → fall back to ime list -s."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.side_effect = [
                _fake_result(stdout="some_value", returncode=1),
                _fake_result(stdout=f"{ADB_KEYBOARD_IME}\n"),
            ]
            assert _make_installer().is_enabled() is True
            assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# is_enabled – IME list fallback
# ---------------------------------------------------------------------------


class TestIsEnabledImeFallback:
    """When settings returns empty/null, ime list -s is used as fallback."""

    def test_ime_list_found(self) -> None:
        """ADB Keyboard in ime list → enabled."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.side_effect = [
                _fake_result(stdout="null"),  # settings fallback
                _fake_result(stdout=f"{ADB_KEYBOARD_IME}\n"),  # ime list
            ]
            assert _make_installer().is_enabled() is True

    def test_ime_list_not_found(self) -> None:
        """ADB Keyboard not in ime list → disabled."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.side_effect = [
                _fake_result(stdout="null"),
                _fake_result(stdout="com.google.android.inputmethod.latin/.LatinIME\n"),
            ]
            assert _make_installer().is_enabled() is False

    def test_ime_list_empty(self) -> None:
        """Both settings and ime list return empty → disabled."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.side_effect = [
                _fake_result(stdout=""),
                _fake_result(stdout=""),
            ]
            assert _make_installer().is_enabled() is False


# ---------------------------------------------------------------------------
# is_enabled – error handling
# ---------------------------------------------------------------------------


class TestIsEnabledErrorHandling:
    def test_ime_list_security_exception_falls_through(self) -> None:
        """If settings succeeds, SecurityException from ime list is irrelevant."""
        settings_output = f"{ADB_KEYBOARD_PACKAGE}/.AdbIME"
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.return_value = _fake_result(stdout=settings_output)
            assert _make_installer().is_enabled() is True
            # Only settings was called – ime list was never reached
            assert mock_run.call_count == 1

    def test_both_commands_fail_returns_false(self) -> None:
        """If both settings and ime list raise exceptions → returns False."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.side_effect = OSError("device offline")
            assert _make_installer().is_enabled() is False


# ---------------------------------------------------------------------------
# is_installed – unaffected
# ---------------------------------------------------------------------------


class TestIsInstalled:
    def test_installed(self) -> None:
        pkg_list = f"package:{ADB_KEYBOARD_PACKAGE}\npackage:com.android.chrome"
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.return_value = _fake_result(stdout=pkg_list)
            assert _make_installer().is_installed() is True

    def test_not_installed(self) -> None:
        pkg_list = "package:com.android.chrome\npackage:com.android.settings"
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.return_value = _fake_result(stdout=pkg_list)
            assert _make_installer().is_installed() is False


# ---------------------------------------------------------------------------
# auto_setup – integration of is_installed + is_enabled
# ---------------------------------------------------------------------------


class TestAutoSetup:
    def test_already_installed_and_enabled(self) -> None:
        """No actions needed when already installed and enabled."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.return_value = _fake_result(
                stdout=f"package:{ADB_KEYBOARD_PACKAGE}\n"
            )
            installer = _make_installer()
            # Mock is_enabled separately
            with patch.object(installer, "is_enabled", return_value=True):
                success, msg = installer.auto_setup()
                assert success is True
                assert "already installed" in msg

    def test_installed_not_enabled_enables(self) -> None:
        """When installed but not enabled, should call enable."""
        with patch(
            "AutoGLM_GUI.adb_plus.keyboard_installer.run_cmd_silently"
        ) as mock_run:
            mock_run.return_value = _fake_result(
                stdout=f"package:{ADB_KEYBOARD_PACKAGE}\n"
            )
            installer = _make_installer()
            with patch.object(installer, "is_enabled", return_value=False):
                with patch.object(
                    installer,
                    "enable",
                    return_value=(True, "ADB Keyboard enabled successfully"),
                ) as mock_enable:
                    success, msg = installer.auto_setup()
                    assert success is True
                    mock_enable.assert_called_once()
