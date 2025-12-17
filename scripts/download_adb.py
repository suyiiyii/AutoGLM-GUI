#!/usr/bin/env python3
"""
ADB 工具自动下载脚本

用法:
    uv run python scripts/download_adb.py          # 下载所有平台（Windows + macOS）
    uv run python scripts/download_adb.py windows  # 只下载 Windows
    uv run python scripts/download_adb.py darwin   # 只下载 macOS

输出目录:
    resources/adb/windows/platform-tools/
    resources/adb/darwin/platform-tools/
"""

import sys
import urllib.request
import zipfile
from pathlib import Path


# Google 官方 Android Platform Tools 下载地址
ADB_URLS = {
    "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
}


def download_with_progress(url: str, output_path: Path) -> None:
    """下载文件并显示进度"""
    print(f"  下载: {url}")

    def reporthook(block_num, block_size, total_size):
        if total_size > 0:
            downloaded = block_num * block_size
            percent = min(100, downloaded * 100 / total_size)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            print(
                f"  进度: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)",
                end="\r",
            )

    try:
        urllib.request.urlretrieve(url, output_path, reporthook=reporthook)
        print()  # 换行
    except Exception as e:
        print(f"\n  ❌ 下载失败: {e}")
        raise


def download_adb(platform: str) -> None:
    """下载并解压 ADB 工具"""
    url = ADB_URLS.get(platform)
    if not url:
        print(f"❌ 不支持的平台: {platform}")
        print(f"   支持的平台: {', '.join(ADB_URLS.keys())}")
        return

    # 项目根目录
    root_dir = Path(__file__).parent.parent
    output_dir = root_dir / "resources" / "adb" / platform
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = output_dir / "platform-tools.zip"

    print(f"\n{'=' * 60}")
    print(f"下载 ADB 工具 - {platform}")
    print(f"{'=' * 60}")

    # 下载
    download_with_progress(url, zip_path)

    # 解压
    print("  解压中...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(output_dir)
        print("  ✓ 解压完成")
    except Exception as e:
        print(f"  ❌ 解压失败: {e}")
        raise

    # 删除 zip 文件
    zip_path.unlink()
    print("  ✓ 清理临时文件")

    # 验证
    platform_tools_dir = output_dir / "platform-tools"
    adb_exe = platform_tools_dir / ("adb.exe" if platform == "windows" else "adb")

    if adb_exe.exists():
        file_size = adb_exe.stat().st_size / (1024 * 1024)
        print(f"  ✓ ADB 可执行文件: {adb_exe} ({file_size:.1f} MB)")
    else:
        print("  ⚠️  警告: 未找到 ADB 可执行文件")

    print(f"\n✓ {platform.upper()} ADB 工具下载完成")
    print(f"  位置: {output_dir}")


def main():
    """主函数"""
    # 默认下载所有平台
    platforms = sys.argv[1:] if len(sys.argv) > 1 else ["windows", "darwin"]

    print("\n" + "=" * 60)
    print("  AutoGLM-GUI - ADB 工具下载器")
    print("=" * 60)
    print(f"  目标平台: {', '.join(platforms)}")

    success_count = 0
    failed_platforms = []

    for platform in platforms:
        try:
            download_adb(platform)
            success_count += 1
        except Exception as e:
            print(f"\n❌ {platform} 下载失败: {e}")
            failed_platforms.append(platform)

    # 总结
    print("\n" + "=" * 60)
    print("  下载总结")
    print("=" * 60)
    print(f"  成功: {success_count}/{len(platforms)}")
    if failed_platforms:
        print(f"  失败: {', '.join(failed_platforms)}")
    print("=" * 60)

    if failed_platforms:
        sys.exit(1)


if __name__ == "__main__":
    main()
