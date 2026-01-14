#!/usr/bin/env python3
"""Generate placeholder screenshots for integration tests.

This script creates minimal placeholder images for test scenarios.
Since the test framework uses Mock LLM and validates coordinates rather
than actual image content, these placeholders are sufficient for testing.
"""

from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("PIL not found, installing...")
    import subprocess

    subprocess.run(["uv", "run", "pip", "install", "pillow"], check=True)
    from PIL import Image


def create_placeholder_image(
    path: Path, index: int, total: int, size: tuple[int, int] = (1080, 2400)
):
    """Create a minimal placeholder image with step number.

    Args:
        path: Where to save the image
        index: Step number (1-based)
        total: Total number of steps
        size: Image dimensions (width, height)
    """
    from PIL import ImageDraw, ImageFont

    # Create white background image
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)

    # Try to use a large font, fall back to default if not available
    try:
        # Try different font sizes for better visibility
        font_large = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 400
        )
        font_small = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 80
        )
    except Exception:
        # Fall back to default font
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Calculate center position
    center_y = size[1] // 2

    # Draw large step number in center
    text = str(index)
    bbox = draw.textbbox((0, 0), text, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    position = ((size[0] - text_width) // 2, center_y - text_height // 2)

    draw.text(position, text, fill="black", font=font_large)

    # Draw small text below showing progress
    progress_text = f"Step {index} of {total}"
    bbox_small = draw.textbbox((0, 0), progress_text, font=font_small)
    small_width = bbox_small[2] - bbox_small[0]
    small_position = ((size[0] - small_width) // 2, center_y + text_height)

    draw.text(small_position, progress_text, fill="gray", font=font_small)

    # Save as PNG
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    print(f"Created: {path.name} (Step {index}/{total})")


def main():
    """Create placeholder screenshots for all test scenarios."""

    # WeChat multi-step test screenshots
    wechat_dir = (
        Path(__file__).parent.parent
        / "tests"
        / "integration"
        / "fixtures"
        / "scenarios"
        / "wechat_multi_step"
    )

    wechat_states = [
        "state_1_home.png",
        "state_2_main.png",
        "state_3_search.png",
        "state_4_search_result.png",
        "state_5_chat_detail.png",
        "state_6_input.png",
        "state_7_typing.png",
        "state_8_sent.png",
        "state_9_back.png",
        "state_10_finished.png",
    ]

    print("=" * 60)
    print("Creating placeholder screenshots for integration tests")
    print("=" * 60)
    print()

    print("Processing: WeChat Multi-Step Test")
    print(f"Directory: {wechat_dir}")
    print()

    for i, state_file in enumerate(wechat_states, start=1):
        create_placeholder_image(
            wechat_dir / state_file, index=i, total=len(wechat_states)
        )

    print()
    print("=" * 60)
    print(f"✓ Created {len(wechat_states)} placeholder screenshots")
    print("=" * 60)


if __name__ == "__main__":
    main()
