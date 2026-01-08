import json
import traceback
from typing import Any, Callable, cast

from openai import OpenAI

from AutoGLM_GUI.actions import ActionHandler, ActionResult
from AutoGLM_GUI.config import AgentConfig, ModelConfig, StepResult
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.prompt_config import get_messages, get_system_prompt

from .message_builder import MessageBuilder
from .parser import GLMParser


class GLMAgent:
    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        device: DeviceProtocol,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        thinking_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config
        self.agent_config = agent_config

        self.openai_client = OpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            timeout=120,
        )
        self.parser = GLMParser()

        self.device = device
        self.action_handler = ActionHandler(
            device=self.device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._is_running = False
        self._thinking_callback = thinking_callback

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

    def _stream_request(
        self,
        messages: list[dict[str, Any]],
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> tuple[str, str, str]:
        stream = self.openai_client.chat.completions.create(
            messages=cast(Any, messages),
            model=self.model_config.model_name,
            max_tokens=self.model_config.max_tokens,
            temperature=self.model_config.temperature,
            top_p=self.model_config.top_p,
            frequency_penalty=self.model_config.frequency_penalty,
            extra_body=self.model_config.extra_body,
            stream=True,
        )

        raw_content = ""
        buffer = ""
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False

        for chunk in stream:
            if len(chunk.choices) == 0:
                continue
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                raw_content += content

                if in_action_phase:
                    continue

                buffer += content

                marker_found = False
                for marker in action_markers:
                    if marker in buffer:
                        thinking_part = buffer.split(marker, 1)[0]
                        if on_thinking_chunk:
                            on_thinking_chunk(thinking_part)
                        in_action_phase = True
                        marker_found = True
                        break

                if marker_found:
                    continue

                is_potential_marker = False
                for marker in action_markers:
                    for i in range(1, len(marker)):
                        if buffer.endswith(marker[:i]):
                            is_potential_marker = True
                            break
                    if is_potential_marker:
                        break

                if not is_potential_marker:
                    if on_thinking_chunk:
                        on_thinking_chunk(buffer)
                    buffer = ""

        thinking, action = self._parse_raw_response(raw_content)
        return thinking, action, raw_content

    def _parse_raw_response(self, content: str) -> tuple[str, str]:
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = parts[0].strip()
            action = "finish(message=" + parts[1]
            return thinking, action

        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = parts[0].strip()
            action = "do(action=" + parts[1]
            return thinking, action

        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = parts[0].replace("<think>", "").replace("</think>", "").strip()
            action = parts[1].replace("</answer>", "").strip()
            return thinking, action

        return "", content

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        self._step_count += 1

        screenshot = self.device.get_screenshot()
        current_app = self.device.get_current_app()

        if is_first:
            system_prompt = self.agent_config.system_prompt
            if system_prompt is None:
                system_prompt = get_system_prompt(self.agent_config.lang)

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
            # 如果有新的用户消息（多轮对话场景），把它加入消息中
            if user_prompt:
                text_content = f"{user_prompt}\n\n** Screen Info **\n\n{screen_info}"
            else:
                # 继续执行当前任务，只需要屏幕信息
                text_content = f"** Screen Info **\n\n{screen_info}"

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

            thinking, action_str, raw_content = self._stream_request(
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
            action = self.parser.parse(action_str)
        except ValueError as e:
            if self.agent_config.verbose:
                logger.warning(f"Failed to parse action: {e}, treating as finish")
            action = {"_metadata": "finish", "message": action_str}

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
                f"<think>{thinking}</think><answer>{action_str}</answer>"
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
            thinking=thinking,
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
