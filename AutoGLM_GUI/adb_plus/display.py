"""ADB display discovery and primary-display selection helpers."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.platform_utils import (
    build_adb_command,
    run_cmd_silently,
    run_cmd_silently_sync,
)


DISPLAY_SELECTION_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class DisplayInfo:
    """Parsed Android display information."""

    logical_id: str
    physical_id: str | None
    width: int
    height: int
    state: str | None


@dataclass(frozen=True)
class DisplaySelection:
    """Selected display ids for screenshot and scrcpy."""

    logical_id: str
    screencap_id: str
    width: int
    height: int
    reason: str


@dataclass(frozen=True)
class _CacheEntry:
    selection: DisplaySelection | None
    expires_at: float


_display_selection_cache: dict[tuple[str, str], _CacheEntry] = {}

_DISPLAY_ID_RE = re.compile(r"\bDisplay\s+(\d+)\b|\bmDisplayId=(\d+)\b")
_DISPLAY_ID_ALT_RE = re.compile(r"\bdisplayId\s+(\d+)\b")
_SIZE_RE = re.compile(r"\b(\d{2,5})\s*[xX\u00d7]\s*(\d{2,5})\b")
_UNIQUE_LOCAL_RE = re.compile(r"\buniqueId\s*=?\s*\"?local:([^\",\s}]+)")
_STATE_RE = re.compile(
    r"\b(?:mState|state|Display State)\s*[:= ]\s*([A-Z_]+)\b",
    re.IGNORECASE,
)
_SURFACE_FLINGER_DISPLAY_ID_RE = re.compile(
    r"\b(?:Display|display)\s+([0-9a-fA-Fx]+)\b"
)


def clear_display_selection_cache(
    device_id: str | None = None,
    adb_path: str = "adb",
) -> None:
    """Clear cached display selections."""
    if device_id is None:
        _display_selection_cache.clear()
        return

    _display_selection_cache.pop(_cache_key(device_id, adb_path), None)


def select_primary_display(
    device_id: str | None = None,
    adb_path: str = "adb",
    ttl_seconds: float = DISPLAY_SELECTION_TTL_SECONDS,
) -> DisplaySelection | None:
    """Select the primary display for a local ADB device."""
    cached = _get_cached_selection(device_id, adb_path)
    if cached is not None:
        return cached.selection

    selection = _select_primary_display_uncached(device_id, adb_path)
    _set_cached_selection(device_id, adb_path, selection, ttl_seconds)
    return selection


async def select_primary_display_async(
    device_id: str | None = None,
    adb_path: str = "adb",
    ttl_seconds: float = DISPLAY_SELECTION_TTL_SECONDS,
) -> DisplaySelection | None:
    """Async primary-display selection for API and streaming paths."""
    cached = _get_cached_selection(device_id, adb_path)
    if cached is not None:
        return cached.selection

    selection = await _select_primary_display_uncached_async(device_id, adb_path)
    _set_cached_selection(device_id, adb_path, selection, ttl_seconds)
    return selection


def _select_primary_display_uncached(
    device_id: str | None,
    adb_path: str,
) -> DisplaySelection | None:
    display_output = _run_adb_text(
        [*build_adb_command(device_id, adb_path), "shell", "dumpsys", "display"],
        timeout=5.0,
    )
    surface_output = _run_adb_text(
        [
            *build_adb_command(device_id, adb_path),
            "shell",
            "dumpsys",
            "SurfaceFlinger",
            "--display-id",
        ],
        timeout=5.0,
    )
    return _select_from_outputs(display_output, surface_output)


async def _select_primary_display_uncached_async(
    device_id: str | None,
    adb_path: str,
) -> DisplaySelection | None:
    display_output = await _run_adb_text_async(
        [*build_adb_command(device_id, adb_path), "shell", "dumpsys", "display"],
        timeout=5.0,
    )
    surface_output = await _run_adb_text_async(
        [
            *build_adb_command(device_id, adb_path),
            "shell",
            "dumpsys",
            "SurfaceFlinger",
            "--display-id",
        ],
        timeout=5.0,
    )
    return _select_from_outputs(display_output, surface_output)


def _select_from_outputs(
    display_output: str,
    surface_output: str,
) -> DisplaySelection | None:
    displays = _parse_dumpsys_display(display_output)
    if not displays:
        return None

    candidates = [display for display in displays if _is_on_state(display.state)]
    reason = "largest_on_display"
    if not candidates:
        candidates = displays
        reason = "largest_parsed_display"

    selected = max(
        candidates,
        key=lambda display: (
            display.width * display.height,
            display.logical_id == "0",
        ),
    )

    surface_ids = _parse_surfaceflinger_display_ids(surface_output)
    screencap_id = selected.physical_id or selected.logical_id
    if selected.physical_id is None and len(displays) == 1 and len(surface_ids) == 1:
        screencap_id = surface_ids[0]
        reason = f"{reason}_surfaceflinger_single_id"

    return DisplaySelection(
        logical_id=selected.logical_id,
        screencap_id=screencap_id,
        width=selected.width,
        height=selected.height,
        reason=reason,
    )


def _parse_dumpsys_display(output: str) -> list[DisplayInfo]:
    sections: list[list[str]] = []
    current: list[str] = []

    for line in output.splitlines():
        if _line_has_display_id(line):
            if current:
                sections.append(current)
            current = [line]
        elif current:
            current.append(line)

    if current:
        sections.append(current)

    displays: list[DisplayInfo] = []
    seen: set[str] = set()
    for section in sections:
        display = _parse_display_section(section)
        if not display or display.logical_id in seen:
            continue
        displays.append(display)
        seen.add(display.logical_id)

    return displays


def _parse_display_section(lines: list[str]) -> DisplayInfo | None:
    text = "\n".join(lines)
    logical_id = _extract_logical_display_id(text)
    if logical_id is None:
        return None

    size = _extract_largest_size(text)
    if size is None:
        return None

    state = _extract_state(text)
    physical_id_match = _UNIQUE_LOCAL_RE.search(text)
    physical_id = physical_id_match.group(1) if physical_id_match else None

    return DisplayInfo(
        logical_id=logical_id,
        physical_id=physical_id,
        width=size[0],
        height=size[1],
        state=state,
    )


def _parse_surfaceflinger_display_ids(output: str) -> list[str]:
    ids: list[str] = []
    for match in _SURFACE_FLINGER_DISPLAY_ID_RE.finditer(output):
        value = match.group(1)
        if value not in ids:
            ids.append(value)
    return ids


def _line_has_display_id(line: str) -> bool:
    return bool(_DISPLAY_ID_RE.search(line) or _DISPLAY_ID_ALT_RE.search(line))


def _extract_logical_display_id(text: str) -> str | None:
    match = _DISPLAY_ID_RE.search(text)
    if match:
        return match.group(1) or match.group(2)

    match = _DISPLAY_ID_ALT_RE.search(text)
    if match:
        return match.group(1)

    return None


def _extract_largest_size(text: str) -> tuple[int, int] | None:
    sizes = [
        (int(match.group(1)), int(match.group(2))) for match in _SIZE_RE.finditer(text)
    ]
    if not sizes:
        return None
    return max(sizes, key=lambda size: size[0] * size[1])


def _extract_state(text: str) -> str | None:
    for match in _STATE_RE.finditer(text):
        value = match.group(1).upper()
        if value in {"ON", "OFF", "DOZE", "DOZE_SUSPEND", "VR", "UNKNOWN"}:
            return value
    return None


def _is_on_state(state: str | None) -> bool:
    return state == "ON"


def _run_adb_text(cmd: list[str], timeout: float) -> str:
    try:
        result = run_cmd_silently_sync(cmd, timeout=timeout)
    except Exception as exc:
        logger.debug("Failed to run display command %s: %s", cmd, exc)
        return ""

    if result.returncode != 0:
        logger.debug("Display command failed %s: %s", cmd, result.stderr)
        return ""

    return result.stdout or ""


async def _run_adb_text_async(cmd: list[str], timeout: float) -> str:
    try:
        result = await run_cmd_silently(cmd, timeout=timeout)
    except Exception as exc:
        logger.debug("Failed to run async display command %s: %s", cmd, exc)
        return ""

    if result.returncode != 0:
        logger.debug("Async display command failed %s: %s", cmd, result.stderr)
        return ""

    return result.stdout or ""


def _get_cached_selection(
    device_id: str | None,
    adb_path: str,
) -> _CacheEntry | None:
    entry = _display_selection_cache.get(_cache_key(device_id, adb_path))
    if entry and entry.expires_at > time.monotonic():
        return entry
    return None


def _set_cached_selection(
    device_id: str | None,
    adb_path: str,
    selection: DisplaySelection | None,
    ttl_seconds: float,
) -> None:
    _display_selection_cache[_cache_key(device_id, adb_path)] = _CacheEntry(
        selection=selection,
        expires_at=time.monotonic() + ttl_seconds,
    )


def _cache_key(device_id: str | None, adb_path: str) -> tuple[str, str]:
    return adb_path, device_id or ""
