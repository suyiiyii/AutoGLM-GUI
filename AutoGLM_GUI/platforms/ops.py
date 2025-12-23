from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# 使用抽象基类 化简代码
class PlatformOpsBase(ABC):
    device_type: str

    @abstractmethod
    def create_agent(
        self,
        *,
        device_id: str | None,
        model_config: Any,
        api_agent_config: Any,
        takeover_callback: Any,
    ) -> tuple[str, Any, Any, str]:
        raise NotImplementedError

    @abstractmethod
    def rebuild_agent(
        self,
        *,
        model_config: Any,
        agent_config: Any,
        takeover_callback: Any,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def tap(
        self,
        *,
        device_id: str | None,
        x: int,
        y: int,
        wda_url: str | None,
        delay: float,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def swipe(
        self,
        *,
        device_id: str | None,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None,
        wda_url: str | None,
        delay: float,
    ) -> None:
        raise NotImplementedError

    def touch_down(
        self, *, device_id: str | None, x: int, y: int, delay: float
    ) -> None:
        raise NotImplementedError

    def touch_move(
        self, *, device_id: str | None, x: int, y: int, delay: float
    ) -> None:
        raise NotImplementedError

    def touch_up(self, *, device_id: str | None, x: int, y: int, delay: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def take_screenshot(
        self,
        *,
        device_id: str | None,
        wda_url: str | None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def list_devices(self, *, initialized_device_ids: set[str]) -> list[dict]:
        raise NotImplementedError


def get_platform_ops(*, device_type: str | None) -> PlatformOpsBase:
    dt = normalize_device_type(device_type)
    if dt == "ios":
        from AutoGLM_GUI.platforms.ios.ops import IOSOps

        return IOSOps()
    if dt == "adb":
        from AutoGLM_GUI.platforms.adb.ops import ADBOps

        return ADBOps()
    raise ValueError(f"Unsupported device type: {dt}")


def normalize_device_type(device_type: str | None) -> str:
    return (device_type or "adb").lower()


def resolve_device_type(*, device_id: str | None, device_type: str | None) -> str:
    dt = normalize_device_type(device_type)  # 默认为 "adb"，并转小写
    if dt != "adb":
        return dt  # 若已指定非 ADB 类型（如 ios），直接返回

    if not device_id:
        return dt  # 无 device_id 时也无法进一步推断

    try:
        from AutoGLM_GUI.state import agent_types, known_device_types

        # 优先从运行时状态中查找该 device_id 对应的类型
        return (
            agent_types.get(device_id) or known_device_types.get(device_id) or dt
        ).lower()
    except Exception:
        return dt  # 出错时 fallback 到默认值


def create_agent(
    *,
    device_type: str | None,
    device_id: str | None,
    model_config: Any,
    api_agent_config: Any,
    takeover_callback: Any,
) -> tuple[str, Any, Any, str]:
    ops = get_platform_ops(device_type=device_type)
    return ops.create_agent(
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
    ops = get_platform_ops(device_type=device_type)
    return ops.rebuild_agent(
        model_config=model_config,
        agent_config=agent_config,
        takeover_callback=takeover_callback,
    )


def tap(
    *,
    device_type: str | None,
    device_id: str | None,
    x: int,
    y: int,
    wda_url: str | None,
    delay: float,
) -> None:
    ops = get_platform_ops(device_type=device_type)
    return ops.tap(device_id=device_id, x=x, y=y, wda_url=wda_url, delay=delay)


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
    ops = get_platform_ops(device_type=device_type)
    return ops.swipe(
        device_id=device_id,
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        duration_ms=duration_ms,
        wda_url=wda_url,
        delay=delay,
    )


def touch_down(
    *, device_type: str | None, device_id: str | None, x: int, y: int, delay: float
) -> None:
    ops = get_platform_ops(device_type=device_type)
    return ops.touch_down(device_id=device_id, x=x, y=y, delay=delay)


def touch_move(
    *, device_type: str | None, device_id: str | None, x: int, y: int, delay: float
) -> None:
    ops = get_platform_ops(device_type=device_type)
    return ops.touch_move(device_id=device_id, x=x, y=y, delay=delay)


def touch_up(
    *, device_type: str | None, device_id: str | None, x: int, y: int, delay: float
) -> None:
    ops = get_platform_ops(device_type=device_type)
    return ops.touch_up(device_id=device_id, x=x, y=y, delay=delay)


def take_screenshot(
    *, device_type: str | None, device_id: str | None, wda_url: str | None
) -> Any:
    ops = get_platform_ops(device_type=device_type)
    return ops.take_screenshot(device_id=device_id, wda_url=wda_url)


def list_devices(*, initialized_device_ids: set[str]) -> list[dict]:
    devices: list[dict] = []

    # ADB
    try:
        from AutoGLM_GUI.platforms.adb.ops import ADBOps

        devices.extend(
            ADBOps().list_devices(initialized_device_ids=initialized_device_ids)
        )
    except Exception:
        pass

    # iOS
    try:
        from AutoGLM_GUI.platforms.ios.ops import IOSOps

        devices.extend(
            IOSOps().list_devices(initialized_device_ids=initialized_device_ids)
        )
    except Exception:
        pass

    return devices
