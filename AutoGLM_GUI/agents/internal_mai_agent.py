"""Internal MAI Agent Implementation

完全内部化实现的 MAI Agent，替代第三方 mai_agent 依赖。

核心特性：
- 多图像历史上下文（保留最近 N 张截图）
- XML 格式的思考过程和动作输出
- 999 坐标系统归一化
- 自动重试机制
"""

import base64
import traceback
from io import BytesIO
from typing import Any, Callable

from PIL import Image

from AutoGLM_GUI.actions import ActionHandler, ActionResult
from AutoGLM_GUI.agents.traj_memory import TrajMemory, TrajStep
from AutoGLM_GUI.config import AgentConfig, ModelConfig, StepResult
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder, ModelClient, VisionModelConfig
from AutoGLM_GUI.parsers.mai_parser import MAIParseError, MAIParser
from AutoGLM_GUI.prompts.mai_prompts import MAI_MOBILE_SYSTEM_PROMPT


class InternalMAIAgent:
    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        device: DeviceProtocol,
        history_n: int = 3,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        thinking_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config
        self.agent_config = agent_config
        self.history_n = history_n

        vision_config = VisionModelConfig(
            base_url=model_config.base_url,
            model_name=model_config.model_name,
            api_key=model_config.api_key,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            frequency_penalty=model_config.frequency_penalty,
            extra_body=model_config.extra_body,
        )

        self.model_client = ModelClient(vision_config)
        self.parser = MAIParser()

        self.device = device
        self.action_handler = ActionHandler(
            device=self.device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self.traj_memory = TrajMemory(task_goal="", task_id="", steps=[])
        self._step_count = 0
        self._is_running = False
        self._thinking_callback = thinking_callback

    def run(self, task: str) -> str:
        self.traj_memory = TrajMemory(task_goal=task, task_id="", steps=[])
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
        is_first = len(self.traj_memory.steps) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        if is_first:
            self.traj_memory.task_goal = task or ""

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        self.traj_memory.clear()
        self._step_count = 0
        self._is_running = False

    def abort(self) -> None:
        self._is_running = False
        logger.info("InternalMAIAgent aborted by user")

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        self._step_count += 1

        screenshot = self.device.get_screenshot()
        current_app = self.device.get_current_app()

        screenshot_bytes = base64.b64decode(screenshot.base64_data)
        pil_image = Image.open(BytesIO(screenshot_bytes))

        if is_first:
            instruction = user_prompt or self.traj_memory.task_goal
        else:
            instruction = self.traj_memory.task_goal

        screen_info = MessageBuilder.build_screen_info(current_app)

        messages = self._build_messages(
            instruction=instruction,
            screen_info=screen_info,
            current_screenshot_base64=screenshot.base64_data,
        )

        try:
            if self.agent_config.verbose:
                print("\n" + "=" * 50)
                print(f"💭 步骤 {self._step_count} - 思考中...")
                print("-" * 50)

            callback = self._thinking_callback
            if callback is None and self.agent_config.verbose:

                def print_chunk(chunk: str) -> None:
                    print(chunk, end="", flush=True)

                callback = print_chunk

            response = self.model_client.request(messages, on_thinking_chunk=callback)
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
            parsed = self.parser.parse_with_thinking(response.action)
            thinking = parsed["thinking"]
            raw_action = parsed["raw_action"]
            converted_action = parsed["converted_action"]
        except MAIParseError as e:
            if self.agent_config.verbose:
                logger.warning(f"Failed to parse action: {e}, treating as finish")
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking=response.thinking or "",
                message=f"Parse error: {e}",
            )

        if self.agent_config.verbose:
            print()
            print("-" * 50)
            print("🎯 动作:")
            print(f"  原始: {raw_action}")
            print(f"  转换: {converted_action}")
            print("=" * 50 + "\n")

        traj_step = TrajStep(
            screenshot=pil_image,
            accessibility_tree=None,
            prediction=response.action,
            action=raw_action,
            conclusion="",
            thought=thinking,
            step_index=self._step_count - 1,
            agent_type="InternalMAIAgent",
            model_name=self.model_config.model_name,
            screenshot_bytes=screenshot_bytes,
            structured_action={"action_json": raw_action},
        )
        self.traj_memory.add_step(traj_step)

        try:
            result = self.action_handler.execute(
                converted_action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = ActionResult(success=False, should_finish=True, message=str(e))

        finished = converted_action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            print("\n" + "🎉 " + "=" * 48)
            print(
                f"✅ 任务完成: {result.message or converted_action.get('message', '完成')}"
            )
            print("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=converted_action,
            thinking=thinking,
            message=result.message or converted_action.get("message"),
        )

    def _build_messages(
        self, instruction: str, screen_info: str, current_screenshot_base64: str
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            MessageBuilder.create_system_message(MAI_MOBILE_SYSTEM_PROMPT),
            MessageBuilder.create_user_message(f"{instruction}\n\n{screen_info}"),
        ]

        history_images = self.traj_memory.get_history_images(self.history_n - 1)
        history_thoughts = self.traj_memory.get_history_thoughts(self.history_n - 1)
        history_actions = self.traj_memory.get_history_actions(self.history_n - 1)

        for idx, (img_bytes, thought, action) in enumerate(
            zip(history_images, history_thoughts, history_actions)
        ):
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            messages.append(
                MessageBuilder.create_user_message(
                    text=screen_info, image_base64=img_base64
                )
            )

            import json

            tool_call_dict = {
                "name": "mobile_use",
                "arguments": action,
            }
            tool_call_json = json.dumps(tool_call_dict, separators=(",", ":"))
            assistant_content = (
                f"<thinking>\n{thought}\n</thinking>\n"
                f"<tool_call>\n{tool_call_json}\n</tool_call>"
            )
            messages.append(MessageBuilder.create_assistant_message(assistant_content))

        messages.append(
            MessageBuilder.create_user_message(
                text=screen_info, image_base64=current_screenshot_base64
            )
        )

        return messages

    @property
    def context(self) -> list[dict[str, Any]]:
        return [
            {
                "step": step.step_index,
                "thought": step.thought,
                "action": step.action,
            }
            for step in self.traj_memory.steps
        ]

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def is_running(self) -> bool:
        return self._is_running
