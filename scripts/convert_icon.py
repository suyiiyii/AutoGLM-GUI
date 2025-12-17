#!/usr/bin/env python3
"""将图标图片转换为 Windows .ico 和 macOS .icns 格式"""

import sys
from pathlib import Path
from PIL import Image

ROOT_DIR = Path(__file__).parent.parent
ELECTRON_DIR = ROOT_DIR / "electron"


def create_ico(source_image_path: Path):
    """创建 Windows .ico 文件（包含多个尺寸）"""
    img = Image.open(source_image_path)

    # 确保是 RGBA 模式
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # 生成多个尺寸
    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for size in sizes:
        resized = img.resize((size, size), Image.Resampling.LANCZOS)
        images.append(resized)

    ico_path = ELECTRON_DIR / "icon.ico"
    images[0].save(ico_path, format="ICO", sizes=[(size, size) for size in sizes])
    print(f"✓ Created Windows icon: {ico_path}")


def create_png_for_icns(source_image_path: Path):
    """创建 1024x1024 PNG（用于生成 .icns）"""
    img = Image.open(source_image_path)

    # 确保是 RGBA 模式
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # 调整为 1024x1024
    img_1024 = img.resize((1024, 1024), Image.Resampling.LANCZOS)

    png_path = ELECTRON_DIR / "icon.png"
    img_1024.save(png_path, format="PNG")
    print(f"✓ Created PNG icon: {png_path}")
    return png_path


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/convert_icon.py <source_image_path>")
        sys.exit(1)

    source_path = Path(sys.argv[1])
    if not source_path.exists():
        print(f"Error: Source image not found: {source_path}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  转换应用图标")
    print("=" * 60)
    print(f"  源文件: {source_path}")

    ELECTRON_DIR.mkdir(exist_ok=True)

    # 创建 Windows .ico
    create_ico(source_path)

    # 创建 PNG（macOS 需要额外工具转换为 .icns）
    create_png_for_icns(source_path)

    print("\n" + "=" * 60)
    print("  下一步: 生成 macOS .icns")
    print("=" * 60)
    print("  运行以下命令:")
    print(f"  cd {ELECTRON_DIR}")
    print("  mkdir -p icon.iconset")
    print("  sips -z 16 16 icon.png --out icon.iconset/icon_16x16.png")
    print("  sips -z 32 32 icon.png --out icon.iconset/icon_16x16@2x.png")
    print("  sips -z 32 32 icon.png --out icon.iconset/icon_32x32.png")
    print("  sips -z 64 64 icon.png --out icon.iconset/icon_32x32@2x.png")
    print("  sips -z 128 128 icon.png --out icon.iconset/icon_128x128.png")
    print("  sips -z 256 256 icon.png --out icon.iconset/icon_128x128@2x.png")
    print("  sips -z 256 256 icon.png --out icon.iconset/icon_256x256.png")
    print("  sips -z 512 512 icon.png --out icon.iconset/icon_256x256@2x.png")
    print("  sips -z 512 512 icon.png --out icon.iconset/icon_512x512.png")
    print("  sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png")
    print("  iconutil -c icns icon.iconset")
    print("  rm -rf icon.iconset")
    print("=" * 60)


if __name__ == "__main__":
    main()
