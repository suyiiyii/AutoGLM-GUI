from __future__ import annotations

import os
from typing import Any

from AutoGLM_GUI.platforms.ops import PlatformOpsBase


def _default_wda_url(wda_url: str | None) -> str:
    return wda_url or os.getenv("PHONE_AGENT_WDA_URL", "http://localhost:8100")


class IOSOps(PlatformOpsBase):
    device_type = "ios"

    def create_agent(
        self,
        *,
        device_id: str | None,
        model_config: Any,
        api_agent_config: Any,
        takeover_callback: Any,
    ) -> tuple[str, Any, Any, str]:
        from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent
        from phone_agent.xctest import list_devices as ios_list_devices

        if not device_id:
            ios_devices = ios_list_devices()
            if not ios_devices:
                raise ValueError(
                    "No iOS devices found. Connect and trust your device, then ensure libimobiledevice + WDA are set up."
                )
            device_id = ios_devices[0].device_id

        wda_url = _default_wda_url(api_agent_config.wda_url)

        agent_config = IOSAgentConfig(
            max_steps=api_agent_config.max_steps,
            wda_url=wda_url,
            device_id=device_id,
            lang=api_agent_config.lang,
            system_prompt=api_agent_config.system_prompt,
            verbose=api_agent_config.verbose,
        )

        agent = IOSPhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
            takeover_callback=takeover_callback,
        )

        return device_id, agent, agent_config, "ios"

    def rebuild_agent(
        self, *, model_config: Any, agent_config: Any, takeover_callback: Any
    ) -> Any:
        from phone_agent.agent_ios import IOSPhoneAgent

        return IOSPhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
            takeover_callback=takeover_callback,
        )

    def tap(
        self,
        *,
        device_id: str | None,
        x: int,
        y: int,
        wda_url: str | None,
        delay: float,
    ) -> None:
        from phone_agent.xctest import tap as ios_tap

        ios_tap(x=x, y=y, wda_url=_default_wda_url(wda_url), delay=delay)

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
        from phone_agent.xctest import swipe as ios_swipe

        duration = None
        if duration_ms is not None:
            duration = duration_ms / 1000.0

        ios_swipe(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            duration=duration,
            wda_url=_default_wda_url(wda_url),
            delay=delay,
        )

    def take_screenshot(self, *, device_id: str | None, wda_url: str | None) -> Any:
        from phone_agent.xctest import get_screenshot

        return get_screenshot(wda_url=_default_wda_url(wda_url), device_id=device_id)

    def list_devices(self, *, initialized_device_ids: set[str]) -> list[dict]:
        from phone_agent.xctest import list_devices as ios_list

        ios_devices = ios_list()

        devices: list[dict] = []
        for d in ios_devices:
            devices.append(
                {
                    "id": d.device_id,
                    "device_type": "ios",
                    "model": d.model or "Unknown",
                    "status": d.status,
                    "connection_type": d.connection_type.value,
                    "is_initialized": d.device_id in initialized_device_ids,
                    "serial": d.device_id.split(" ")[0],
                    "device_name": d.device_name,
                    "ios_version": d.ios_version,
                }
            )
        return devices
