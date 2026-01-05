"""OpenAI-compatible model client with streaming support."""

import time
from typing import Any, Callable

from openai import OpenAI

from .types import ModelResponse, VisionModelConfig


class ModelClient:
    def __init__(self, config: VisionModelConfig):
        self.config = config
        self.client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout,
        )

    def request(
        self,
        messages: list[dict[str, Any]],
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        start_time = time.time()
        time_to_first_token = None
        time_to_thinking_end = None

        stream = self.client.chat.completions.create(
            messages=messages,
            model=self.config.model_name,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            frequency_penalty=self.config.frequency_penalty,
            extra_body=self.config.extra_body,
            stream=True,
        )

        raw_content = ""
        buffer = ""
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False
        first_token_received = False

        for chunk in stream:
            if len(chunk.choices) == 0:
                continue
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                raw_content += content

                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True

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

                        if time_to_thinking_end is None:
                            time_to_thinking_end = time.time() - start_time

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

        total_time = time.time() - start_time

        thinking, action = self._parse_response(raw_content)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    # TODO parser 应该独立出来形成一个接口，这是因为不同模型要求的  parser 可能是不一样的
    def _parse_response(self, raw_content: str) -> tuple[str, str]:
        thinking = ""
        action = ""

        if "<think>" in raw_content and "</think>" in raw_content:
            start = raw_content.find("<think>") + len("<think>")
            end = raw_content.find("</think>")
            thinking = raw_content[start:end].strip()

        if "<answer>" in raw_content and "</answer>" in raw_content:
            start = raw_content.find("<answer>") + len("<answer>")
            end = raw_content.find("</answer>")
            action = raw_content[start:end].strip()
        elif "<answer>" in raw_content:
            start = raw_content.find("<answer>") + len("<answer>")
            action = raw_content[start:].strip()
        else:
            lines = raw_content.strip().split("\n")
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("do(") or line.startswith("finish("):
                    action = line
                    thinking_lines = []
                    for content_line in lines:
                        if content_line.strip() == action:
                            break
                        thinking_lines.append(content_line)
                    thinking = "\n".join(thinking_lines).strip()
                    break

            if not action:
                action = raw_content.replace(thinking, "").strip()

        return thinking, action
