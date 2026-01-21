"""Builder for constructing multimodal chat messages."""

from typing import Any


class MessageBuilder:
    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str, image_base64: str | None = None
    ) -> dict[str, Any]:
        if image_base64 is None:
            return {"role": "user", "content": text}

        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                },
            ],
        }

    @staticmethod
    def create_multi_image_user_message(
        text: str, image_base64_list: list[str]
    ) -> dict[str, Any]:
        if not image_base64_list:
            return {"role": "user", "content": text}

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": text}]

        for image_base64 in image_base64_list:
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                }
            )

        return {"role": "user", "content": content_parts}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        if message["role"] != "user":
            return message

        content = message["content"]
        if isinstance(content, str):
            return message

        text_parts = [part for part in content if part["type"] == "text"]
        if len(text_parts) == 1:
            return {"role": "user", "content": text_parts[0]["text"]}

        return {"role": "user", "content": text_parts}

    @staticmethod
    def build_screen_info(current_app: str) -> str:
        return f"** Screen Info **\n\nCurrent App: {current_app}"
