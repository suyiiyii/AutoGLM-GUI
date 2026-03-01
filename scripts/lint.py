#!/usr/bin/env python3
"""
AutoGLM-GUI 统一 Lint 脚本
支持前后端代码检查和格式化
"""

import argparse
import subprocess
import sys
import platform
from pathlib import Path


class LintResult:
    """Lint 检查结果"""

    def __init__(self, name: str, success: bool, output: str = "", error: str = ""):
        self.name = name
        self.success = success
        self.output = output
        self.error = error

    def __bool__(self) -> bool:
        return self.success


class AutoGLMLinter:
    """AutoGLM-GUI 统一代码检查器"""

    # Windows 上需要通过 shell 执行的 Node.js 包管理器命令
    _NODE_PACKAGE_MANAGERS = frozenset(["pnpm", "npm", "yarn", "npx"])

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.frontend_dir = root_dir / "frontend"
        self.backend_dir = root_dir
        self._platform = platform.system()

    def _should_use_shell(self, cmd: list[str]) -> bool:
        """判断命令是否需要通过 shell 执行（Windows 平台的 Node.js 工具）"""
        return self._platform == "Windows" and cmd[0] in self._NODE_PACKAGE_MANAGERS

    def run_command(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        capture_output: bool = True,
    ) -> LintResult:
        """执行命令并返回结果"""
        name = " ".join(cmd[:3])
        work_dir = cwd or self.root_dir

        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=capture_output,
                text=True,
                timeout=300,  # 5分钟超时
                shell=self._should_use_shell(cmd),
            )
            return LintResult(
                name=name,
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return LintResult(
                name=name,
                success=False,
                error="命令执行超时 (5分钟)",
            )
        except FileNotFoundError:
            return LintResult(
                name=name,
                success=False,
                error=f"命令未找到: {cmd[0]}",
            )
        except Exception as e:
            return LintResult(
                name=name,
                success=False,
                error=f"执行错误: {str(e)}",
            )

    def lint_frontend_eslint(self, fix: bool = False) -> LintResult:
        """运行 ESLint 检查前端代码"""
        if not (self.frontend_dir / "package.json").exists():
            return LintResult(
                name="ESLint (前端)",
                success=True,
                output="跳过: 前端目录不存在",
            )

        cmd = ["pnpm", "lint"]
        if fix:
            cmd.append("--fix")

        print(f"🔍 运行: {' '.join(cmd)} (前端)")
        result = self.run_command(cmd, self.frontend_dir)

        if result.success:
            print("✅ ESLint 检查通过")
        else:
            print("❌ ESLint 检查失败")
            if result.error:
                print(f"错误: {result.error[:500]}...")

        return result

    def lint_frontend_format(self, check_only: bool = False) -> LintResult:
        """检查前端代码格式化 (Prettier)"""
        if not (self.frontend_dir / "package.json").exists():
            return LintResult(
                name="Prettier (前端)",
                success=True,
                output="跳过: 前端目录不存在",
            )

        cmd = ["pnpm", "format:check" if check_only else "format"]

        print(f"🎨 运行: {' '.join(cmd)} (前端)")
        result = self.run_command(cmd, self.frontend_dir)

        if check_only:
            if result.success:
                print("✅ Prettier 格式检查通过")
            else:
                print("❌ Prettier 格式检查失败")
                print("💡 使用 --fix 参数来自动格式化代码")
        else:
            if result.success:
                print("✅ 代码格式化完成")
            else:
                print("❌ 代码格式化失败")

        return result

    def lint_frontend_types(self) -> LintResult:
        """运行 TypeScript 类型检查"""
        if not (self.frontend_dir / "package.json").exists():
            return LintResult(
                name="TypeScript 类型检查",
                success=True,
                output="跳过: 前端目录不存在",
            )

        cmd = ["pnpm", "type-check"]

        print(f"🔷 运行: {' '.join(cmd)} (前端)")
        result = self.run_command(cmd, self.frontend_dir)

        if result.success:
            print("✅ TypeScript 类型检查通过")
        else:
            print("❌ TypeScript 类型检查失败")
            if result.error:
                print(f"错误: {result.error[:500]}...")

        return result

    def lint_backend_ruff(self, fix: bool = False) -> LintResult:
        """运行 Ruff 检查后端代码"""
        if not (self.root_dir / "pyproject.toml").exists():
            return LintResult(
                name="Ruff 检查 (后端)",
                success=True,
                output="跳过: 后端项目不存在",
            )

        cmd = ["uv", "run", "ruff", "check"]
        if fix:
            cmd.append("--fix")

        print(f"🐍 运行: {' '.join(cmd)} (后端)")
        result = self.run_command(cmd, self.backend_dir)

        if result.success:
            print("✅ Ruff 检查通过")
        else:
            print("❌ Ruff 检查失败")
            if result.output:
                print(f"发现的问题:\n{result.output[:1000]}...")

        return result

    def lint_backend_format(self, check_only: bool = False) -> LintResult:
        """检查后端代码格式化 (Ruff)"""
        if not (self.root_dir / "pyproject.toml").exists():
            return LintResult(
                name="Ruff 格式化 (后端)",
                success=True,
                output="跳过: 后端项目不存在",
            )

        cmd = ["uv", "run", "ruff", "format"]
        if check_only:
            cmd.append("--check")

        print(f"🎨 运行: {' '.join(cmd)} (后端)")
        result = self.run_command(cmd, self.backend_dir)

        if check_only:
            if result.success:
                print("✅ Ruff 格式检查通过")
            else:
                print("❌ Ruff 格式检查失败")
                print("💡 使用 --fix 参数来自动格式化代码")
        else:
            if result.success:
                print("✅ 代码格式化完成")
            else:
                print("❌ 代码格式化失败")

        return result

    def lint_backend_types(self) -> LintResult:
        """运行 Pyright 类型检查 (Python 3.11 兼容性)"""
        if not (self.root_dir / "pyproject.toml").exists():
            return LintResult(
                name="Pyright 类型检查 (后端)",
                success=True,
                output="跳过: 后端项目不存在",
            )

        # 使用 pyrightconfig.json 中的配置 (Python 3.11)
        cmd = ["uv", "run", "pyright", "AutoGLM_GUI/"]

        print(f"🔷 运行: {' '.join(cmd)} (后端)")
        result = self.run_command(cmd, self.backend_dir)

        if result.success:
            print("✅ Pyright 类型检查通过 (Python 3.11 兼容)")
        else:
            print("❌ Pyright 类型检查失败")
            if result.output:
                # 只显示错误摘要，不显示全部输出
                lines = result.output.strip().split("\n")
                error_lines = [line for line in lines if "error:" in line.lower()]
                if error_lines:
                    print(f"发现 {len(error_lines)} 个类型错误:")
                    # 最多显示前 10 个错误
                    for line in error_lines[:10]:
                        print(f"  {line}")
                    if len(error_lines) > 10:
                        print(f"  ... 还有 {len(error_lines) - 10} 个错误")

        return result

    def lint_frontend(
        self, fix: bool = False, check_only: bool = False
    ) -> list[LintResult]:
        """运行前端所有检查"""
        print("\n📱 前端代码检查")
        print("=" * 50)

        results = []

        # ESLint 检查
        results.append(self.lint_frontend_eslint(fix=fix))

        # Prettier 格式检查
        if not fix:
            results.append(self.lint_frontend_format(check_only=True))
        else:
            results.append(self.lint_frontend_format(check_only=False))

        # TypeScript 类型检查
        results.append(self.lint_frontend_types())

        return results

    def lint_backend(
        self, fix: bool = False, check_only: bool = False
    ) -> list[LintResult]:
        """运行后端所有检查"""
        print("\n🐍 后端代码检查")
        print("=" * 50)

        results = []

        # Ruff 检查
        results.append(self.lint_backend_ruff(fix=fix))

        # Ruff 格式检查
        if not fix:
            results.append(self.lint_backend_format(check_only=True))
        else:
            results.append(self.lint_backend_format(check_only=False))

        # Pyright 类型检查 (Python 3.11 兼容性)
        results.append(self.lint_backend_types())

        return results

    def lint_all(
        self,
        fix: bool = False,
        frontend_only: bool = False,
        backend_only: bool = False,
    ) -> bool:
        """运行所有检查"""
        print("🚀 AutoGLM-GUI 代码检查工具")
        print("=" * 50)

        all_results = []

        if frontend_only:
            results = self.lint_frontend(fix=fix)
            all_results.extend(results)
        elif backend_only:
            results = self.lint_backend(fix=fix)
            all_results.extend(results)
        else:
            # 运行前端和后端检查
            results = self.lint_frontend(fix=fix)
            all_results.extend(results)

            results = self.lint_backend(fix=fix)
            all_results.extend(results)

        # 显示总结
        print("\n📊 检查总结")
        print("=" * 50)

        passed = sum(1 for r in all_results if r.success)
        total = len(all_results)

        for result in all_results:
            status = "✅ 通过" if result.success else "❌ 失败"
            print(f"{status} {result.name}")

        print(f"\n结果: {passed}/{total} 项检查通过")

        if not all(r.success for r in all_results):
            print("\n💡 建议:")
            if not fix:
                print("   - 运行不带 --check-only 参数来自动修复一些问题")
            print("   - 检查上面的详细错误信息")
            print("   - 确保已安装所有依赖:")
            print("     前端: cd frontend && pnpm install")
            print("     后端: uv sync")
            print("   - 或者直接运行: uv run python scripts/lint.py")

        return all(r.success for r in all_results)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="AutoGLM-GUI 前后端代码检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                     # 检查并自动修复所有问题 (默认)
  %(prog)s --check-only       # 仅检查，不修复
  %(prog)s --frontend         # 仅检查前端代码
  %(prog)s --backend          # 仅检查后端代码
  %(prog)s --frontend --check-only  # 仅检查前端，不修复
        """,
    )

    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅检查，不修复 (默认会修复)",
    )
    parser.add_argument(
        "--frontend",
        action="store_true",
        help="仅检查前端代码",
    )
    parser.add_argument(
        "--backend",
        action="store_true",
        help="仅检查后端代码",
    )

    args = parser.parse_args()

    # 默认修复问题，除非指定 --check-only
    fix = not args.check_only

    # 验证参数
    if args.frontend and args.backend:
        print("❌ 不能同时指定 --frontend 和 --backend")
        sys.exit(1)

    # 获取项目根目录
    root_dir = Path(__file__).parent.parent
    if not (root_dir / "pyproject.toml").exists():
        print("❌ 无法找到项目根目录 (pyproject.toml)")
        sys.exit(1)

    # 创建检查器并运行
    linter = AutoGLMLinter(root_dir)
    success = linter.lint_all(
        fix=fix,
        frontend_only=args.frontend,
        backend_only=args.backend,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
