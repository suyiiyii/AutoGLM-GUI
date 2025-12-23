from __future__ import annotations

from typing import Any


def normalize_device_type(device_type: str | None) -> str:
    return (device_type or "adb").lower()


def resolve_device_type(*, device_id: str | None, device_type: str | None) -> str:
    dt = normalize_device_type(device_type)
    if dt != "adb":
        return dt

    if not device_id:
        return dt

    try:
        from AutoGLM_GUI.state import agent_types, known_device_types

        return (agent_types.get(device_id) or known_device_types.get(device_id) or dt).lower()
    except Exception:
        return dt


def create_agent(
    *,
    device_type: str | None,
    device_id: str | None,
    model_config: Any,
    api_agent_config: Any,
    takeover_callback: Any,
) -> tuple[str, Any, Any, str]:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        from AutoGLM_GUI.platforms.ios.ops import create_agent as ios_create

        return ios_create(
            device_id=device_id,
            model_config=model_config,
            api_agent_config=api_agent_config,
            takeover_callback=takeover_callback,
        )

    from AutoGLM_GUI.platforms.adb.ops import create_agent as adb_create

    return adb_create(
        device_id=device_id,
        model_config=model_config,
        api_agent_config=api_agent_config,
        takeover_callback=takeover_callback,
    )


def rebuild_agent(
    *,
    device_type: str | None,
    model_config: Any,
    agent_config: Any,
    takeover_callback: Any,
) -> Any:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        from AutoGLM_GUI.platforms.ios.ops import rebuild_agent as ios_rebuild

        return ios_rebuild(
            model_config=model_config,
            agent_config=agent_config,
            takeover_callback=takeover_callback,
        )

    from AutoGLM_GUI.platforms.adb.ops import rebuild_agent as adb_rebuild

    return adb_rebuild(
        model_config=model_config,
        agent_config=agent_config,
        takeover_callback=takeover_callback,
    )


def tap(*, device_type: str | None, device_id: str | None, x: int, y: int, wda_url: str | None, delay: float) -> None:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        from AutoGLM_GUI.platforms.ios.ops import tap as ios_tap

        return ios_tap(x=x, y=y, wda_url=wda_url, delay=delay)

    from AutoGLM_GUI.platforms.adb.ops import tap as adb_tap

    return adb_tap(x=x, y=y, device_id=device_id, delay=delay)


def swipe(
    *,
    device_type: str | None,
    device_id: str | None,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None,
    wda_url: str | None,
    delay: float,
) -> None:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        from AutoGLM_GUI.platforms.ios.ops import swipe as ios_swipe

        return ios_swipe(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            duration_ms=duration_ms,
            wda_url=wda_url,
            delay=delay,
        )

    from AutoGLM_GUI.platforms.adb.ops import swipe as adb_swipe

    return adb_swipe(
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        duration_ms=duration_ms,
        device_id=device_id,
        delay=delay,
    )


def touch_down(*, device_type: str | None, device_id: str | None, x: int, y: int, delay: float) -> None:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        raise NotImplementedError("not_supported_for_ios")

    from AutoGLM_GUI.platforms.adb.touch import touch_down as adb_touch_down

    return adb_touch_down(x=x, y=y, device_id=device_id, delay=delay)


def touch_move(*, device_type: str | None, device_id: str | None, x: int, y: int, delay: float) -> None:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        raise NotImplementedError("not_supported_for_ios")

    from AutoGLM_GUI.platforms.adb.touch import touch_move as adb_touch_move

    return adb_touch_move(x=x, y=y, device_id=device_id, delay=delay)


def touch_up(*, device_type: str | None, device_id: str | None, x: int, y: int, delay: float) -> None:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        raise NotImplementedError("not_supported_for_ios")

    from AutoGLM_GUI.platforms.adb.touch import touch_up as adb_touch_up

    return adb_touch_up(x=x, y=y, device_id=device_id, delay=delay)


def take_screenshot(*, device_type: str | None, device_id: str | None, wda_url: str | None) -> Any:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        from AutoGLM_GUI.platforms.ios.ops import take_screenshot as ios_ss

        return ios_ss(device_id=device_id, wda_url=wda_url)

    from AutoGLM_GUI.platforms.adb.ops import take_screenshot as adb_ss

    return adb_ss(device_id=device_id)


def list_devices(*, initialized_device_ids: set[str]) -> list[dict]:
    devices: list[dict] = []

    from AutoGLM_GUI.platforms.adb.ops import list_devices as adb_list

    devices.extend(adb_list(initialized_device_ids=initialized_device_ids))

    try:
        from AutoGLM_GUI.platforms.ios.ops import list_devices as ios_list

        devices.extend(ios_list(initialized_device_ids=initialized_device_ids))
    except Exception:
        pass

    return devices
