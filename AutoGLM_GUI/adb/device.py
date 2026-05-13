"""Device control utilities for Android automation."""

import subprocess

from AutoGLM_GUI.adb.apps import APP_PACKAGES
from AutoGLM_GUI.adb.timing import TIMING_CONFIG
from AutoGLM_GUI.platform_utils import build_adb_command
from AutoGLM_GUI.trace import trace_sleep, trace_span


def get_current_app(device_id: str | None = None) -> str:
    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.get_current_app",
        attrs={"device_id": device_id},
    ):
        result = subprocess.run(
            adb_prefix + ["shell", "dumpsys", "window"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    output = result.stdout
    if not output:
        raise ValueError("No output from dumpsys window")

    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

    return "System Home"


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.tap",
        attrs={"device_id": device_id, "x": x, "y": y, "delay_ms": delay * 1000},
    ):
        subprocess.run(
            adb_prefix + ["shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            check=True,
        )
    trace_sleep(
        delay,
        name="sleep.device_tap_delay",
        attrs={"device_id": device_id},
    )


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.double_tap",
        attrs={"device_id": device_id, "x": x, "y": y, "delay_ms": delay * 1000},
    ):
        subprocess.run(
            adb_prefix + ["shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            check=True,
        )
        trace_sleep(
            TIMING_CONFIG.device.double_tap_interval,
            name="sleep.device_double_tap_interval",
            attrs={"device_id": device_id},
        )
        subprocess.run(
            adb_prefix + ["shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            check=True,
        )
    trace_sleep(
        delay,
        name="sleep.device_double_tap_delay",
        attrs={"device_id": device_id},
    )


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.long_press",
        attrs={
            "device_id": device_id,
            "x": x,
            "y": y,
            "duration_ms": duration_ms,
            "delay_ms": delay * 1000,
        },
    ):
        subprocess.run(
            adb_prefix
            + [
                "shell",
                "input",
                "swipe",
                str(x),
                str(y),
                str(x),
                str(y),
                str(duration_ms),
            ],
            capture_output=True,
            check=True,
        )
    trace_sleep(
        delay,
        name="sleep.device_long_press_delay",
        attrs={"device_id": device_id},
    )


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = build_adb_command(device_id)

    if duration_ms is None:
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))

    with trace_span(
        "adb.swipe",
        attrs={
            "device_id": device_id,
            "start_x": start_x,
            "start_y": start_y,
            "end_x": end_x,
            "end_y": end_y,
            "duration_ms": duration_ms,
            "delay_ms": delay * 1000,
        },
    ):
        subprocess.run(
            adb_prefix
            + [
                "shell",
                "input",
                "swipe",
                str(start_x),
                str(start_y),
                str(end_x),
                str(end_y),
                str(duration_ms),
            ],
            capture_output=True,
            check=True,
        )
    trace_sleep(
        delay,
        name="sleep.device_swipe_delay",
        attrs={"device_id": device_id},
    )


def back(device_id: str | None = None, delay: float | None = None) -> None:
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.back",
        attrs={"device_id": device_id, "delay_ms": delay * 1000},
    ):
        subprocess.run(
            adb_prefix + ["shell", "input", "keyevent", "4"],
            capture_output=True,
            check=True,
        )
    trace_sleep(
        delay,
        name="sleep.device_back_delay",
        attrs={"device_id": device_id},
    )


def home(device_id: str | None = None, delay: float | None = None) -> None:
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = build_adb_command(device_id)

    with trace_span(
        "adb.home",
        attrs={"device_id": device_id, "delay_ms": delay * 1000},
    ):
        subprocess.run(
            adb_prefix + ["shell", "input", "keyevent", "KEYCODE_HOME"],
            capture_output=True,
            check=True,
        )
    trace_sleep(
        delay,
        name="sleep.device_home_delay",
        attrs={"device_id": device_id},
    )


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    if app_name not in APP_PACKAGES:
        return False

    adb_prefix = build_adb_command(device_id)
    package = APP_PACKAGES[app_name]

    with trace_span(
        "adb.launch_app",
        attrs={
            "device_id": device_id,
            "app_name": app_name,
            "delay_ms": delay * 1000,
        },
    ):
        subprocess.run(
            adb_prefix
            + [
                "shell",
                "monkey",
                "-p",
                package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            capture_output=True,
            check=True,
        )
    trace_sleep(
        delay,
        name="sleep.device_launch_delay",
        attrs={"device_id": device_id, "app_name": app_name},
    )
    return True
