"""Input utilities for Android device text input."""

import base64
import subprocess
from collections.abc import Sequence

from AutoGLM_GUI.adb_plus.keyboard_installer import (
    ADB_KEYBOARD_IME,
    ADB_KEYBOARD_PACKAGE,
)
from AutoGLM_GUI.platform_utils import build_adb_command, run_cmd_silently
from AutoGLM_GUI.trace import trace_span


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}{result.stderr}".strip()


def _require_adb_ime_current(current_ime: str, detail: str) -> None:
    if ADB_KEYBOARD_IME not in current_ime:
        raise RuntimeError(
            f"Failed to switch to ADB Keyboard (current={current_ime!r}; {detail})"
        )


def type_text(text: str, device_id: str | None = None) -> None:
    # Empty --es values fail as missing args on some OEM am broadcast implementations.
    if text == "":
        return

    adb_prefix = build_adb_command(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    with trace_span(
        "adb.type_text",
        attrs={"device_id": device_id, "text_length": len(text)},
    ):
        subprocess.run(
            adb_prefix
            + [
                "shell",
                "am",
                "broadcast",
                "-a",
                "ADB_INPUT_B64",
                "--es",
                "msg",
                encoded_text,
            ],
            capture_output=True,
            text=True,
            check=True,
        )


async def type_text_async(text: str, device_id: str | None = None) -> None:
    if text == "":
        return

    adb_prefix = build_adb_command(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    with trace_span(
        "adb.type_text",
        attrs={"device_id": device_id, "text_length": len(text)},
    ):
        await run_cmd_silently(
            adb_prefix
            + [
                "shell",
                "am",
                "broadcast",
                "-a",
                "ADB_INPUT_B64",
                "--es",
                "msg",
                encoded_text,
            ],
        )


def clear_text(device_id: str | None = None) -> None:
    adb_prefix = build_adb_command(device_id)

    with trace_span("adb.clear_text", attrs={"device_id": device_id}):
        subprocess.run(
            adb_prefix + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
            capture_output=True,
            text=True,
            check=True,
        )


async def clear_text_async(device_id: str | None = None) -> None:
    adb_prefix = build_adb_command(device_id)

    with trace_span("adb.clear_text", attrs={"device_id": device_id}):
        await run_cmd_silently(
            adb_prefix + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
        )


def _read_default_ime(adb_prefix: Sequence[str]) -> str:
    result = subprocess.run(
        list(adb_prefix)
        + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
        check=True,
    )
    return _combined_output(result)


def _is_adb_ime_enabled(adb_prefix: Sequence[str]) -> bool:
    """Return True if ADB Keyboard is already in the enabled IME list.

    Reads ``enabled_input_methods`` first. ``ime list -s`` is only a
    fallback because some OEM ROMs raise SecurityException on it.
    """
    result = subprocess.run(
        list(adb_prefix)
        + ["shell", "settings", "get", "secure", "enabled_input_methods"],
        capture_output=True,
        text=True,
        check=False,
    )
    enabled_imes = result.stdout.strip()
    if enabled_imes and enabled_imes != "null" and result.returncode == 0:
        return ADB_KEYBOARD_PACKAGE in enabled_imes or ADB_KEYBOARD_IME in enabled_imes

    listed = subprocess.run(
        list(adb_prefix) + ["shell", "ime", "list", "-s"],
        capture_output=True,
        text=True,
        check=False,
    )
    return ADB_KEYBOARD_IME in _combined_output(listed)


def _enable_and_set_adb_keyboard(adb_prefix: Sequence[str]) -> None:
    enable_out = "skipped, already enabled"
    if not _is_adb_ime_enabled(adb_prefix):
        enable = subprocess.run(
            list(adb_prefix) + ["shell", "ime", "enable", ADB_KEYBOARD_IME],
            capture_output=True,
            text=True,
            check=False,
        )
        enable_out = _combined_output(enable)
    set_ime = subprocess.run(
        list(adb_prefix) + ["shell", "ime", "set", ADB_KEYBOARD_IME],
        capture_output=True,
        text=True,
        check=False,
    )
    current_ime = _read_default_ime(adb_prefix)
    _require_adb_ime_current(
        current_ime,
        f"enable={enable_out!r}, set={_combined_output(set_ime)!r}",
    )


async def _read_default_ime_async(adb_prefix: Sequence[str]) -> str:
    result = await run_cmd_silently(
        list(adb_prefix)
        + ["shell", "settings", "get", "secure", "default_input_method"],
    )
    return _combined_output(result)


async def _is_adb_ime_enabled_async(adb_prefix: Sequence[str]) -> bool:
    result = await run_cmd_silently(
        list(adb_prefix)
        + ["shell", "settings", "get", "secure", "enabled_input_methods"],
    )
    enabled_imes = result.stdout.strip()
    if enabled_imes and enabled_imes != "null" and result.returncode == 0:
        return ADB_KEYBOARD_PACKAGE in enabled_imes or ADB_KEYBOARD_IME in enabled_imes

    listed = await run_cmd_silently(
        list(adb_prefix) + ["shell", "ime", "list", "-s"],
    )
    return ADB_KEYBOARD_IME in _combined_output(listed)


async def _enable_and_set_adb_keyboard_async(adb_prefix: Sequence[str]) -> None:
    enable_out = "skipped, already enabled"
    if not await _is_adb_ime_enabled_async(adb_prefix):
        enable = await run_cmd_silently(
            list(adb_prefix) + ["shell", "ime", "enable", ADB_KEYBOARD_IME],
        )
        enable_out = _combined_output(enable)
    set_ime = await run_cmd_silently(
        list(adb_prefix) + ["shell", "ime", "set", ADB_KEYBOARD_IME],
    )
    current_ime = await _read_default_ime_async(adb_prefix)
    _require_adb_ime_current(
        current_ime,
        f"enable={enable_out!r}, set={_combined_output(set_ime)!r}",
    )


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.detect_adb_keyboard",
        attrs={"device_id": device_id},
    ):
        current_ime = _read_default_ime(adb_prefix)

    if ADB_KEYBOARD_IME not in current_ime:
        with trace_span(
            "adb.set_adb_keyboard",
            attrs={"device_id": device_id},
        ):
            _enable_and_set_adb_keyboard(adb_prefix)

    type_text("", device_id)

    return current_ime


async def detect_and_set_adb_keyboard_async(device_id: str | None = None) -> str:
    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.detect_adb_keyboard",
        attrs={"device_id": device_id},
    ):
        current_ime = await _read_default_ime_async(adb_prefix)

    if ADB_KEYBOARD_IME not in current_ime:
        with trace_span(
            "adb.set_adb_keyboard",
            attrs={"device_id": device_id},
        ):
            await _enable_and_set_adb_keyboard_async(adb_prefix)

    await type_text_async("", device_id)

    return current_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.restore_keyboard",
        attrs={"device_id": device_id},
    ):
        subprocess.run(
            adb_prefix + ["shell", "ime", "set", ime],
            capture_output=True,
            text=True,
            check=True,
        )


async def restore_keyboard_async(ime: str, device_id: str | None = None) -> None:
    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.restore_keyboard",
        attrs={"device_id": device_id},
    ):
        await run_cmd_silently(
            adb_prefix + ["shell", "ime", "set", ime],
        )
