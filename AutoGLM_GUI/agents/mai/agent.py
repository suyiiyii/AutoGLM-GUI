"""Internal MAI Agent Implementation

完全内部化实现的 MAI Agent，替代第三方 mai_agent 依赖。

核心特性：
- 多图像历史上下文（保留最近 N 张截图）
- XML 格式的思考过程和动作输出
- 999 坐标系统归一化
- 自动重试机制
"""

import base64
import time
import traceback
from io import BytesIO
from typing import Any, Callable

from openai import OpenAI
from PIL import Image

from AutoGLM_GUI.actions import ActionHandler, ActionResult
from AutoGLM_GUI.config import AgentConfig, ModelConfig, StepResult
from AutoGLM_GUI.device_protocol import DeviceProtocol
from AutoGLM_GUI.logger import logger
from AutoGLM_GUI.model import MessageBuilder

from .traj_memory import TrajMemory, TrajStep
from .parser import MAIParseError, MAIParser
from .prompts import MAI_MOBILE_SYSTEM_PROMPT


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

        self.openai_client = OpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            timeout=120,
        )
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

        self._total_llm_time = 0.0
        self._total_action_time = 0.0
        self._total_tokens = 0

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
        elif task:
            # 多轮对话：有新的用户消息，更新 task_goal
            self.traj_memory.task_goal = task

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        self.traj_memory.clear()
        self._step_count = 0
        self._is_running = False
        self._total_llm_time = 0.0
        self._total_action_time = 0.0
        self._total_tokens = 0

    def abort(self) -> None:
        self._is_running = False
        logger.info("InternalMAIAgent aborted by user")

    def _stream_request(
        self,
        messages: list[dict[str, Any]],
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> str:
        stream = self.openai_client.chat.completions.create(
            messages=messages,  # type: ignore[arg-type]
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
        action_markers = ["</thinking>", "<tool_call>"]
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

        return raw_content

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

        max_retries = 3
        raw_content = ""
        thinking = ""
        raw_action = None
        converted_action = None

        for attempt in range(max_retries):
            try:
                if self.agent_config.verbose:
                    retry_info = (
                        f" (尝试 {attempt + 1}/{max_retries})" if attempt > 0 else ""
                    )
                    print("\n" + "=" * 50)
                    print(f"💭 步骤 {self._step_count}{retry_info} - 思考中...")
                    print("-" * 50)

                callback = self._thinking_callback
                if callback is None and self.agent_config.verbose:

                    def print_chunk(chunk: str) -> None:
                        print(chunk, end="", flush=True)

                    callback = print_chunk

                llm_start = time.time()
                raw_content = self._stream_request(messages, on_thinking_chunk=callback)
                llm_time = time.time() - llm_start
                self._total_llm_time += llm_time

                if self.agent_config.verbose:
                    print(f"\n⏱️  LLM 耗时: {llm_time:.2f}s")

                parsed = self.parser.parse_with_thinking(raw_content)
                thinking = parsed["thinking"]
                raw_action = parsed["raw_action"]
                converted_action = parsed["converted_action"]

                break

            except MAIParseError as e:
                if self.agent_config.verbose:
                    logger.warning(f"解析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return StepResult(
                        success=False,
                        finished=True,
                        action=None,
                        thinking="",
                        message=f"Parse error after {max_retries} retries: {e}",
                    )
                continue

            except Exception as e:
                if self.agent_config.verbose:
                    logger.warning(
                        f"模型调用失败 (尝试 {attempt + 1}/{max_retries}): {e}"
                    )
                if attempt == max_retries - 1:
                    if self.agent_config.verbose:
                        traceback.print_exc()
                    return StepResult(
                        success=False,
                        finished=True,
                        action=None,
                        thinking="",
                        message=f"Model error after {max_retries} retries: {e}",
                    )
                continue

        if not raw_content or raw_action is None or converted_action is None:
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking=thinking,
                message="Failed to get valid response after retries",
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
            prediction=raw_content,
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
            action_start = time.time()
            result = self.action_handler.execute(
                converted_action, screenshot.width, screenshot.height
            )
            action_time = time.time() - action_start
            self._total_action_time += action_time

            if self.agent_config.verbose:
                print(f"⚡ 动作执行耗时: {action_time:.2f}s")
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
            print("=" * 50)
            print("\n📊 性能统计:")
            print(f"  总步数: {self._step_count}")
            print(f"  总 LLM 耗时: {self._total_llm_time:.2f}s")
            print(f"  总动作耗时: {self._total_action_time:.2f}s")
            print(
                f"  平均每步耗时: {(self._total_llm_time + self._total_action_time) / self._step_count:.2f}s"
            )
            if self._total_tokens > 0:
                print(f"  总 Token 使用: {self._total_tokens}")
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
        system_prompt = self.agent_config.system_prompt or MAI_MOBILE_SYSTEM_PROMPT

        messages: list[dict[str, Any]] = [
            MessageBuilder.create_system_message(system_prompt),
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
