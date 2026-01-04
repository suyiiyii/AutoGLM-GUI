"""Adapter to bridge GLMAgent to BaseAgent protocol."""

from typing import Any, Callable

from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

from AutoGLM_GUI.device_manager import DeviceManager
from AutoGLM_GUI.devices.adb_device import ADBDevice
from AutoGLM_GUI.model import ModelConfig as GLMModelConfig

from .glm_agent import GLMAgent, GLMAgentConfig
from .protocols import StepResult


class GLMAgentAdapter:
    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        thinking_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config
        self.agent_config = agent_config

        device_manager = DeviceManager.get_instance()
        if not agent_config.device_id:
            raise ValueError("device_id is required for GLM Agent v2")

        managed = device_manager.get_device_by_device_id(agent_config.device_id)
        if not managed:
            raise ValueError(f"Device {agent_config.device_id} not found")

        if managed.connection_type.value == "remote":
            remote_device = device_manager.get_remote_device_instance(managed.serial)
            if not remote_device:
                raise ValueError(f"Remote device instance not found: {managed.serial}")
            device = remote_device
        else:
            device = ADBDevice(managed.primary_device_id)

        glm_model_config = GLMModelConfig(
            base_url=model_config.base_url,
            model_name=model_config.model_name,
            api_key=model_config.api_key,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            frequency_penalty=model_config.frequency_penalty,
            extra_body=model_config.extra_body,
        )

        glm_agent_config = GLMAgentConfig(
            max_steps=agent_config.max_steps,
            lang=agent_config.lang,
            system_prompt=agent_config.system_prompt,
            verbose=agent_config.verbose,
        )

        self._agent = GLMAgent(
            device=device,
            model_config=glm_model_config,
            agent_config=glm_agent_config,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            thinking_callback=thinking_callback,
        )

        glm_agent_config = GLMAgentConfig(
            max_steps=agent_config.max_steps,
            lang=agent_config.lang,
            system_prompt=agent_config.system_prompt,
            verbose=agent_config.verbose,
        )

        self._agent = GLMAgent(
            device=device,
            model_config=glm_model_config,
            agent_config=glm_agent_config,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

    def run(self, task: str) -> str:
        return self._agent.run(task)

    def step(self, task: str | None = None) -> StepResult:
        return self._agent.step(task)

    def reset(self) -> None:
        self._agent.reset()

    def abort(self) -> None:
        self._agent.abort()

    @property
    def context(self) -> list[dict[str, Any]]:
        return self._agent.context

    @property
    def step_count(self) -> int:
        return self._agent.step_count

    @property
    def is_running(self) -> bool:
        return self._agent.is_running
