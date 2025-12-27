"""
Monkey patches for phone_agent to add streaming functionality.

This module patches the upstream phone_agent code without modifying the original files.
"""

from typing import Any, Callable

from phone_agent.model import ModelClient


# Store original methods
_original_model_request = ModelClient.request


def _patched_model_request(
    self,
    messages: list[dict[str, Any]],
    on_thinking_chunk: Callable[[str], None] | None = None,
) -> Any:
    """
    Patched version of ModelClient.request that supports streaming thinking chunks.

    This wraps the original request method and adds callback support for thinking chunks.
    """
    import time

    from phone_agent.model.client import ModelResponse

    # Start timing
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
    buffer = ""  # Buffer to hold content that might be part of a marker
    action_markers = ["finish(message=", "do(action="]
    in_action_phase = False  # Track if we've entered the action phase
    first_token_received = False

    for chunk in stream:
        if len(chunk.choices) == 0:
            continue
        if chunk.choices[0].delta.content is not None:
            content = chunk.choices[0].delta.content
            raw_content += content

            # Record time to first token
            if not first_token_received:
                time_to_first_token = time.time() - start_time
                first_token_received = True

            if in_action_phase:
                # Already in action phase, just accumulate content without printing
                continue

            buffer += content

            # Check if any marker is fully present in buffer
            marker_found = False
            for marker in action_markers:
                if marker in buffer:
                    # Marker found, print everything before it
                    thinking_part = buffer.split(marker, 1)[0]
                    print(thinking_part, end="", flush=True)
                    if on_thinking_chunk:
                        on_thinking_chunk(thinking_part)
                    print()  # Print newline after thinking is complete
                    in_action_phase = True
                    marker_found = True

                    # Record time to thinking end
                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time

                    break

            if marker_found:
                continue  # Continue to collect remaining content

            # Check if buffer ends with a prefix of any marker
            # If so, don't print yet (wait for more content)
            is_potential_marker = False
            for marker in action_markers:
                for i in range(1, len(marker)):
                    if buffer.endswith(marker[:i]):
                        is_potential_marker = True
                        break
                if is_potential_marker:
                    break

            if not is_potential_marker:
                # Safe to print the buffer
                print(buffer, end="", flush=True)
                if on_thinking_chunk:
                    on_thinking_chunk(buffer)
                buffer = ""

    # Calculate total time
    total_time = time.time() - start_time

    # Parse thinking and action from response
    thinking, action = self._parse_response(raw_content)

    # Print performance metrics
    from phone_agent.config.i18n import get_message

    lang = self.config.lang
    print()
    print("=" * 50)
    print(f"⏱️  {get_message('performance_metrics', lang)}:")
    print("-" * 50)
    if time_to_first_token is not None:
        print(f"{get_message('time_to_first_token', lang)}: {time_to_first_token:.3f}s")
    if time_to_thinking_end is not None:
        print(
            f"{get_message('time_to_thinking_end', lang)}:        {time_to_thinking_end:.3f}s"
        )
    print(f"{get_message('total_inference_time', lang)}:          {total_time:.3f}s")
    print("=" * 50)

    return ModelResponse(
        thinking=thinking,
        action=action,
        raw_content=raw_content,
        time_to_first_token=time_to_first_token,
        time_to_thinking_end=time_to_thinking_end,
        total_time=total_time,
    )


def apply_patches():
    """Apply all monkey patches to phone_agent."""
    # Patch ModelClient.request to support streaming callbacks
    ModelClient.request = _patched_model_request
