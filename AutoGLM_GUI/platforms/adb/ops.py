from __future__ import annotations

from typing import Any

from AutoGLM_GUI.platforms.adb.screenshot import capture_screenshot
from AutoGLM_GUI.platforms.adb.serial import get_device_serial
from AutoGLM_GUI.platforms.ops import PlatformOpsBase


class ADBOps(PlatformOpsBase):
    device_type = "adb"

    def create_agent(
        self,
        *,
        device_id: str | None,
        model_config: Any,
        api_agent_config: Any,
        takeover_callback: Any,
    ) -> tuple[str, Any, Any, str]:
        if not device_id:
            raise ValueError("device_id is required in agent_config")

        from phone_agent import PhoneAgent
        from phone_agent.agent import AgentConfig

        agent_config = AgentConfig(
            max_steps=api_agent_config.max_steps,
            device_id=device_id,
            lang=api_agent_config.lang,
            system_prompt=api_agent_config.system_prompt,
            verbose=api_agent_config.verbose,
        )

        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
            takeover_callback=takeover_callback,
        )

        return device_id, agent, agent_config, "adb"

    def rebuild_agent(
        self, *, model_config: Any, agent_config: Any, takeover_callback: Any
    ) -> Any:
        from phone_agent import PhoneAgent

        return PhoneAgent(
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
        from phone_agent.adb import tap as adb_tap

        adb_tap(x=x, y=y, device_id=device_id, delay=delay)

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
        from phone_agent.adb import swipe as adb_swipe

        adb_swipe(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            duration_ms=duration_ms,
            device_id=device_id,
            delay=delay,
        )

    def touch_down(
        self, *, device_id: str | None, x: int, y: int, delay: float
    ) -> None:
        from AutoGLM_GUI.platforms.adb.touch import touch_down as adb_touch_down

        return adb_touch_down(x=x, y=y, device_id=device_id, delay=delay)

    def touch_move(
        self, *, device_id: str | None, x: int, y: int, delay: float
    ) -> None:
        from AutoGLM_GUI.platforms.adb.touch import touch_move as adb_touch_move

        return adb_touch_move(x=x, y=y, device_id=device_id, delay=delay)

    def touch_up(self, *, device_id: str | None, x: int, y: int, delay: float) -> None:
        from AutoGLM_GUI.platforms.adb.touch import touch_up as adb_touch_up

        return adb_touch_up(x=x, y=y, device_id=device_id, delay=delay)

    def take_screenshot(self, *, device_id: str | None, wda_url: str | None) -> Any:
        return capture_screenshot(device_id=device_id)

    def list_devices(self, *, initialized_device_ids: set[str]) -> list[dict]:
        from phone_agent.adb import list_devices as adb_list, ADBConnection

        adb_devices = adb_list()
        conn = ADBConnection()

        devices: list[dict] = []
        for d in adb_devices:
            serial = get_device_serial(d.device_id, conn.adb_path)
            devices.append(
                {
                    "id": d.device_id,
                    "device_type": "adb",
                    "model": d.model or "Unknown",
                    "status": d.status,
                    "connection_type": d.connection_type.value,
                    "is_initialized": d.device_id in initialized_device_ids,
                    "serial": serial,
                }
            )

        return devices
