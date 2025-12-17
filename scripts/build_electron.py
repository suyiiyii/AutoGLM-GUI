#!/usr/bin/env python3
"""
AutoGLM-GUI Electron 一键构建脚本

功能：
1. 检查环境依赖
2. 同步 Python 开发依赖
3. 构建前端
4. 下载 ADB 工具
5. 打包 Python 后端
6. 构建 Electron 应用

用法：
    uv run python scripts/build_electron.py [--skip-frontend] [--skip-adb] [--skip-backend]
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# 修复 Windows 编码问题
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


class Color:
    """终端颜色"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"


def print_step(step: str, total: int, current: int):
    """打印步骤信息"""
    print(f"\n{Color.CYAN}{Color.BOLD}[{current}/{total}] {step}{Color.RESET}")
    print("=" * 60)


def print_success(message: str):
    """打印成功信息"""
    print(f"{Color.GREEN}✓ {message}{Color.RESET}")


def print_error(message: str):
    """打印错误信息"""
    print(f"{Color.RED}✗ {message}{Color.RESET}", file=sys.stderr)


def print_warning(message: str):
    """打印警告信息"""
    print(f"{Color.YELLOW}⚠ {message}{Color.RESET}")


def run_command(cmd: list[str], cwd: Path | None = None, check: bool = True) -> bool:
    """执行命令"""
    cmd_str = " ".join(str(c) for c in cmd)
    print(f"{Color.BLUE}$ {cmd_str}{Color.RESET}")

    try:
        # Windows 下 pnpm/npm 等命令需要通过 shell 执行
        use_shell = sys.platform == "win32" and cmd[0] in ["pnpm", "npm"]

        result = subprocess.run(
            cmd, cwd=cwd, check=check, capture_output=False, text=True, shell=use_shell
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print_error(f"命令执行失败: {e}")
        return False
    except FileNotFoundError:
        print_error(f"命令未找到: {cmd[0]}")
        return False


def check_command(cmd: str) -> bool:
    """检查命令是否可用"""
    try:
        # Windows 下某些命令（如 pnpm）需要通过 shell 执行
        subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            check=True,
            shell=(sys.platform == "win32"),
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


class ElectronBuilder:
    def __init__(self, args):
        self.args = args
        self.root_dir = Path(__file__).parent.parent
        self.frontend_dir = self.root_dir / "frontend"
        self.scripts_dir = self.root_dir / "scripts"
        self.electron_dir = self.root_dir / "electron"
        self.resources_dir = self.root_dir / "resources"

        # 平台信息
        self.platform = platform.system().lower()
        self.is_windows = self.platform == "windows"
        self.is_macos = self.platform == "darwin"
        self.is_linux = self.platform == "linux"

    def check_environment(self) -> bool:
        """检查环境依赖"""
        print_step("检查环境依赖", 7, 1)

        required_tools = {
            "uv": "Python 包管理器",
            "node": "Node.js 运行时",
            "pnpm": "pnpm 包管理器",
        }

        missing_tools = []
        for tool, description in required_tools.items():
            if check_command(tool):
                print_success(f"{description} ({tool}) 已安装")
            else:
                print_error(f"{description} ({tool}) 未安装")
                missing_tools.append(tool)

        if missing_tools:
            print_error(f"\n缺少必需工具: {', '.join(missing_tools)}")
            print("\n安装指南:")
            if "uv" in missing_tools:
                print("  uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
            if "node" in missing_tools:
                print("  Node.js: https://nodejs.org/")
            if "pnpm" in missing_tools:
                print("  pnpm: npm install -g pnpm")
            return False

        return True

    def sync_python_deps(self) -> bool:
        """同步 Python 开发依赖"""
        print_step("同步 Python 开发依赖", 7, 2)
        return run_command(["uv", "sync", "--dev"], cwd=self.root_dir)

    def build_frontend(self) -> bool:
        """构建前端"""
        print_step("构建前端", 7, 3)

        # 安装前端依赖
        print("\n安装前端依赖...")
        if not run_command(["pnpm", "install"], cwd=self.frontend_dir):
            return False

        # 构建前端
        print("\n构建前端代码...")
        if not run_command(["pnpm", "build"], cwd=self.frontend_dir):
            return False

        # 复制前端构建产物到后端 static 目录
        print("\n复制前端到后端...")
        frontend_dist = self.frontend_dir / "dist"
        backend_static = self.root_dir / "AutoGLM_GUI" / "static"

        if backend_static.exists():
            shutil.rmtree(backend_static)

        shutil.copytree(frontend_dist, backend_static)
        print_success(f"前端已复制到 {backend_static}")

        return True

    def download_adb(self) -> bool:
        """下载 ADB 工具"""
        print_step("下载 ADB 工具", 7, 4)

        # 确定要下载的平台
        platforms = []
        if self.is_windows:
            platforms.append("windows")
        elif self.is_macos:
            platforms.extend(["darwin", "windows"])  # macOS 上构建两个平台
        else:
            print_warning("Linux 平台暂不支持，跳过 Windows ADB 下载")
            platforms.append("darwin")

        # 下载 ADB
        for plat in platforms:
            print(f"\n下载 {plat} ADB...")
            if not run_command(
                ["uv", "run", "python", "scripts/download_adb.py", plat],
                cwd=self.root_dir,
            ):
                return False

        return True

    def build_backend(self) -> bool:
        """打包 Python 后端"""
        print_step("打包 Python 后端", 7, 5)

        # 运行 PyInstaller
        print("\n运行 PyInstaller...")
        if not run_command(["pyinstaller", "autoglm.spec"], cwd=self.scripts_dir):
            return False

        # 复制到 resources/backend
        print("\n复制后端到 resources...")
        backend_dist = self.scripts_dir / "dist" / "autoglm-gui"
        backend_resources = self.resources_dir / "backend"

        if backend_resources.exists():
            shutil.rmtree(backend_resources)

        shutil.copytree(backend_dist, backend_resources)
        print_success(f"后端已复制到 {backend_resources}")

        return True

    def build_electron(self) -> bool:
        """构建 Electron 应用"""
        print_step("安装 Electron 依赖", 7, 6)

        # 安装 Electron 依赖
        if not run_command(["npm", "install"], cwd=self.electron_dir):
            return False

        print_step("构建 Electron 应用", 7, 7)

        # 构建 Electron
        if not run_command(["npm", "run", "build"], cwd=self.electron_dir):
            return False

        # 显示构建产物
        print("\n" + "=" * 60)
        print(f"{Color.GREEN}{Color.BOLD}✓ 构建完成！{Color.RESET}")
        print("=" * 60)

        dist_dir = self.electron_dir / "dist"
        if dist_dir.exists():
            print(f"\n构建产物位置: {dist_dir}")
            print("\n文件列表:")
            for item in sorted(dist_dir.iterdir()):
                if item.is_file():
                    size = item.stat().st_size / (1024 * 1024)
                    print(f"  - {item.name} ({size:.1f} MB)")
                elif item.is_dir() and not item.name.startswith("."):
                    print(f"  - {item.name}/ (目录)")

        return True

    def build(self) -> bool:
        """执行完整构建流程"""
        print(f"\n{Color.BOLD}AutoGLM-GUI Electron 构建工具{Color.RESET}")
        print(f"平台: {self.platform}")
        print(f"项目根目录: {self.root_dir}\n")

        steps = [
            ("环境检查", lambda: self.check_environment()),
            ("Python 依赖", lambda: self.sync_python_deps()),
            (
                "前端构建",
                lambda: self.build_frontend()
                if not self.args.skip_frontend
                else (print_warning("跳过前端构建"), True)[1],
            ),
            (
                "ADB 工具",
                lambda: self.download_adb()
                if not self.args.skip_adb
                else (print_warning("跳过 ADB 下载"), True)[1],
            ),
            (
                "后端打包",
                lambda: self.build_backend()
                if not self.args.skip_backend
                else (print_warning("跳过后端打包"), True)[1],
            ),
            ("Electron", lambda: self.build_electron()),
        ]

        for step_name, step_func in steps:
            if not step_func():
                print_error(f"\n构建失败: {step_name}")
                return False

        return True


def main():
    parser = argparse.ArgumentParser(description="AutoGLM-GUI Electron 一键构建脚本")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    parser.add_argument("--skip-adb", action="store_true", help="跳过 ADB 工具下载")
    parser.add_argument("--skip-backend", action="store_true", help="跳过后端打包")
    args = parser.parse_args()

    builder = ElectronBuilder(args)

    try:
        success = builder.build()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print_error("\n\n构建已取消")
        sys.exit(1)
    except Exception as e:
        print_error(f"\n\n构建失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
