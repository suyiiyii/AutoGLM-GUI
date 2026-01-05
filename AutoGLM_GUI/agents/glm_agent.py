"""GLM Agent implementation with full control over the agent lifecycle."""

import json
import traceback
from typing import Any, Callable

from AutoGLM_GUI.actions import ActionHandler, ActionResult, parse_action
from AutoGLM_GUI.config import AgentConfig, ModelConfig, StepResult
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder, ModelClient, VisionModelConfig
from phone_agent.config import get_messages, get_system_prompt


class GLMAgent:
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

        glm_model_config = VisionModelConfig(
            base_url=model_config.base_url,
            model_name=model_config.model_name,
            api_key=model_config.api_key,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            frequency_penalty=model_config.frequency_penalty,
            extra_body=model_config.extra_body,
        )

        self.model_client = ModelClient(glm_model_config)

        self.device = self._resolve_device(agent_config.device_id)
        self.action_handler = ActionHandler(
            device=self.device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._is_running = False
        self._thinking_callback = thinking_callback

    @staticmethod
    def _resolve_device(device_id: str | None) -> DeviceProtocol:
        from AutoGLM_GUI.device_manager import DeviceManager
        from AutoGLM_GUI.devices.adb_device import ADBDevice

        if not device_id:
            raise ValueError("device_id is required for GLM Agent")

        device_manager = DeviceManager.get_instance()
        managed = device_manager.get_device_by_device_id(device_id)

        if not managed:
            raise ValueError(f"Device {device_id} not found")

        if managed.connection_type.value == "remote":
            remote_device = device_manager.get_remote_device_instance(managed.serial)
            if not remote_device:
                raise ValueError(f"Remote device instance not found: {managed.serial}")
            return remote_device  # type: ignore[return-value]
        else:
            return ADBDevice(managed.primary_device_id)

    def run(self, task: str) -> str:
        self._context = []
        self._step_count = 0
        self._is_running = True

        try:
            result = self._execute_step(task, is_first=True)

            if result.finished:
                return result.message or "Task completed"

            while self._step_count < self.agent_config.max_steps and self._is_running:
                result = self._execute_step(is_first=False)

                if result.finished:
                    return result.message or "Task completed"

            return "Max steps reached"
        finally:
            self._is_running = False

    def step(self, task: str | None = None) -> StepResult:
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        self._context = []
        self._step_count = 0
        self._is_running = False

    def abort(self) -> None:
        self._is_running = False
        logger.info("Agent aborted by user")

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        self._step_count += 1

        screenshot = self.device.get_screenshot()
        current_app = self.device.get_current_app()

        if is_first:
            system_prompt = self.agent_config.system_prompt or get_system_prompt(
                self.agent_config.lang
            )
            self._context.append(MessageBuilder.create_system_message(system_prompt))

            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"{user_prompt}\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = screen_info

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        try:
            msgs = get_messages(self.agent_config.lang)
            if self.agent_config.verbose:
                print("\n" + "=" * 50)
                print(f"💭 {msgs['thinking']}:")
                print("-" * 50)

            callback = self._thinking_callback
            if callback is None and self.agent_config.verbose:

                def print_chunk(chunk: str) -> None:
                    print(chunk, end="", flush=True)

                callback = print_chunk

            response = self.model_client.request(
                self._context, on_thinking_chunk=callback
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )

        try:
            action = parse_action(response.action)
        except ValueError as e:
            if self.agent_config.verbose:
                logger.warning(f"Failed to parse action: {e}, treating as finish")
            action = {"_metadata": "finish", "message": response.action}

        if self.agent_config.verbose:
            print()
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        try:
            result = self.action_handler.execute(
                action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = ActionResult(success=False, should_finish=True, message=str(e))

        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "🎉 " + "=" * 48)
            print(
                f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )
            print("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        return self._context.copy()

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def is_running(self) -> bool:
        return self._is_running
