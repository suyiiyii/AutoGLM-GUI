from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "android-agent/settings.gradle.kts",
    "android-agent/build.gradle.kts",
    "android-agent/gradle.properties",
    "android-agent/app/build.gradle.kts",
    "android-agent/app/src/main/AndroidManifest.xml",
    "android-agent/app/src/main/java/com/autoglm/agent/MainActivity.kt",
    "android-agent/app/src/main/java/com/autoglm/agent/http/AgentHttpServer.kt",
    "android-agent/app/src/main/java/com/autoglm/agent/projection/ScreenCaptureController.kt",
    "android-agent/app/src/main/java/com/autoglm/agent/service/AgentForegroundService.kt",
    "android-agent/app/src/main/java/com/autoglm/agent/service/DeviceAccessibilityService.kt",
    "android-agent/app/src/main/res/layout/activity_main.xml",
    "android-agent/app/src/main/res/xml/accessibility_service_config.xml",
]


def assert_exists(relative_path: str) -> None:
    path = REPO_ROOT / relative_path
    if not path.exists():
        raise AssertionError(f"Missing required file: {relative_path}")


def assert_contains(relative_path: str, snippet: str) -> None:
    content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    if snippet not in content:
        raise AssertionError(f"{relative_path} is missing snippet: {snippet}")


def main() -> int:
    for relative_path in REQUIRED_FILES:
        assert_exists(relative_path)

    assert_contains(
        "android-agent/app/src/main/java/com/autoglm/agent/http/AgentHttpServer.kt",
        '"/device/$deviceId/screenshot"',
    )
    assert_contains(
        "android-agent/app/src/main/java/com/autoglm/agent/http/AgentHttpServer.kt",
        '"/device/$deviceId/tap"',
    )
    assert_contains(
        "android-agent/app/src/main/java/com/autoglm/agent/http/AgentHttpServer.kt",
        '"/device/$deviceId/swipe"',
    )
    assert_contains(
        "android-agent/app/src/main/java/com/autoglm/agent/http/AgentHttpServer.kt",
        '"/device/$deviceId/type_text"',
    )
    assert_contains(
        "android-agent/app/src/main/java/com/autoglm/agent/http/AgentHttpServer.kt",
        '"/device/$deviceId/current_app"',
    )

    print("android-agent scaffold check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
