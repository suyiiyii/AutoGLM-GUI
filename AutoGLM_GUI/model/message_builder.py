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

        return MessageBuilder.create_user_message_with_images(
            text=text,
            images=[{"mime_type": "image/png", "data": image_base64}],
        )

    @staticmethod
    def create_user_message_with_images(
        text: str, images: list[dict[str, str]]
    ) -> dict[str, Any]:
        if not images:
            return {"role": "user", "content": text}

        content_parts: list[dict[str, Any]] = []
        for image in images:
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image['mime_type']};base64,{image['data']}"
                    },
                }
            )

        # Images first, then text — matches the official Open-AutoGLM input layout.
        content_parts.append({"type": "text", "text": text})
        return {
            "role": "user",
            "content": content_parts,
        }

    @staticmethod
    def create_multi_image_user_message(
        text: str, image_base64_list: list[str]
    ) -> dict[str, Any]:
        if not image_base64_list:
            return {"role": "user", "content": text}

        return MessageBuilder.create_user_message_with_images(
            text=text,
            images=[
                {"mime_type": "image/png", "data": image_base64}
                for image_base64 in image_base64_list
            ],
        )

    @staticmethod
    def build_user_reference_images_notice(image_count: int) -> str:
        if image_count <= 0:
            return ""
        image_word = "image" if image_count == 1 else "images"
        return (
            f"User attached {image_count} reference {image_word}. "
            "Image 1 is the current Android screen and is the only image that "
            "defines tap/swipe coordinates. Use the following attached images "
            "only as reference material for the user's task."
        )

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """Drop image parts from a message, keeping the text parts as a list.

        Mirrors the official Open-AutoGLM behaviour: after a request the
        screenshot is stripped from the user turn so that history never
        carries stale images into later requests. String content (system /
        assistant turns) is returned unchanged.
        """
        content = message.get("content")
        if not isinstance(content, list):
            return message

        text_parts = [
            part
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return {**message, "content": text_parts}

    @staticmethod
    def build_screen_info(current_app: str) -> str:
        return f"** Screen Info **\n\nCurrent App: {current_app}"
