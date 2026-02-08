#!/usr/bin/env python3
"""
AutoGLM-GUI ast-grep 代码质量检查脚本.

使用 ast-grep 进行 Python 代码模式检查，支持多种规则配置。
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class RuleConfig:
    """ast-grep 规则配置"""

    rule_id: str  # 唯一标识符
    name: str  # 人类可读名称
    description: str  # 规则描述
    severity: Literal["error", "warning", "info"]  # 严重程度
    pattern: str  # ast-grep 模式（仅 rule 部分）
    lang: str = "python"  # 语言


@dataclass
class RuleResult:
    """单个规则的检查结果"""

    rule: RuleConfig
    passed: bool  # 是否通过检查
    matches: list[dict] = field(default_factory=list)  # 匹配的结果
    error: str = ""  # 错误信息（如果有）


class AstGrepChecker:
    """ast-grep 代码质量检查器"""

    # 类常量
    SEVERITY_ICONS = {"error": "🚨", "warning": "⚠️", "info": "ℹ️"}
    MAX_MATCHES_TO_DISPLAY = 5  # 最多显示的匹配数量
    TIMEOUT_SECONDS = 15  # 超时时间（秒）

    # 检查规则配置（使用简单的 ast-grep 表达式）
    RULES: dict[str, RuleConfig] = {
        "no-print": RuleConfig(
            rule_id="no-print",
            name="检测 print() 语句",
            description="应使用 logger 而非 print()",
            severity="warning",
            pattern="print($$$)",  # $$$ 匹配任意数量的参数
        ),
    }

    def __init__(self, root_dir: Path):
        """初始化检查器

        Args:
            root_dir: 项目根目录
        """
        self.root_dir = root_dir
        self.backend_dir = root_dir / "AutoGLM_GUI"

    def check_rule(self, rule: RuleConfig) -> RuleResult:
        """检查单个规则

        Args:
            rule: 规则配置

        Returns:
            RuleResult: 检查结果
        """
        try:
            # 使用 -p 参数传递模式
            cmd = [
                "sg",
                "run",
                "-p",
                rule.pattern,
                "--json",
                "-l",
                rule.lang,
                "AutoGLM_GUI/",
            ]

            result = subprocess.run(
                cmd,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT_SECONDS,
            )

            # 检查 stderr
            if result.stderr.strip():
                return RuleResult(
                    rule=rule,
                    passed=False,
                    matches=[],
                    error=f"ast-grep 错误: {result.stderr.strip()}",
                )

            # 检查退出码
            if result.returncode != 0 and not result.stdout.strip():
                return RuleResult(
                    rule=rule,
                    passed=False,
                    matches=[],
                    error=f"ast-grep 执行失败 (退出码: {result.returncode})",
                )

            # 解析 JSON 输出
            matches = []
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    if isinstance(data, list):
                        matches = data
                    elif isinstance(data, dict):
                        matches = data.get("matches", [])
                        if "errors" in data:
                            return RuleResult(
                                rule=rule,
                                passed=False,
                                matches=[],
                                error=f"ast-grep 规则错误: {data['errors']}",
                            )
                except json.JSONDecodeError as e:
                    return RuleResult(
                        rule=rule, passed=False, matches=[], error=f"JSON 解析失败: {e}"
                    )

            passed = len(matches) == 0
            return RuleResult(rule=rule, passed=passed, matches=matches)

        except subprocess.TimeoutExpired:
            return RuleResult(
                rule=rule,
                passed=False,
                matches=[],
                error=f"检查超时（超过 {self.TIMEOUT_SECONDS} 秒）",
            )
        except FileNotFoundError:
            return RuleResult(
                rule=rule,
                passed=False,
                matches=[],
                error="未找到 ast-grep (sg) 命令，请运行: npm install -g ast-grep",
            )
        except Exception:
            return RuleResult(
                rule=rule, passed=False, matches=[], error="检查过程中发生未知错误"
            )

    def format_rule_result(self, result: RuleResult) -> None:
        """格式化并打印单个规则结果

        Args:
            result: 规则检查结果
        """
        # 选择图标
        status_icon = "✅" if result.passed else "❌"
        severity_icon = self.SEVERITY_ICONS[result.rule.severity]

        # 打印规则状态
        if result.error:
            # 有错误信息
            print(f"{status_icon} {severity_icon} {result.rule.name} - {result.error}")
        else:
            # 正常状态
            print(f"{status_icon} {severity_icon} {result.rule.name}")

        # 如果未通过且有匹配，显示匹配位置
        if not result.passed and result.matches:
            # 最多显示前 N 个匹配
            display_count = min(self.MAX_MATCHES_TO_DISPLAY, len(result.matches))
            for match in result.matches[:display_count]:
                if not isinstance(match, dict):
                    # 跳过无效匹配
                    continue

                file_path = match.get("file", "unknown")
                range_info = match.get("range", {})
                start = range_info.get("start", {})
                line = start.get("line", "?")
                column = start.get("column", "?")
                print(f"   📍 {file_path}:{line}:{column}")

            # 如果有更多匹配，显示省略信息
            if len(result.matches) > display_count:
                remaining = len(result.matches) - display_count
                print(f"   ... 还有 {remaining} 个匹配")

    def print_summary(self, results: list[RuleResult]) -> None:
        """打印检查汇总

        Args:
            results: 所有规则的检查结果
        """
        print("\n📊 检查总结")
        print("=" * 50)

        passed = sum(1 for r in results if r.passed)
        total = len(results)

        # 打印每个规则的状态
        for result in results:
            status_icon = "✅" if result.passed else "❌"
            print(f"{status_icon} {result.rule.name}")

        print(f"\n结果: {passed}/{total} 项检查通过")

        # 如果有失败的规则，提供建议
        failed_results = [r for r in results if not r.passed]
        if failed_results:
            print("\n💡 建议:")
            for result in failed_results:
                print(f"   - {result.rule.description}")

            print("\n📝 修复方式:")
            print("   ast-grep 不支持自动修复，请手动修改代码")
            print("   参考文档: https://ast-grep.github.io/")

    def check_all(self, rule_ids: list[str] | None = None) -> bool:
        """检查所有规则或指定规则

        Args:
            rule_ids: 要检查的规则 ID 列表，None 表示检查所有规则

        Returns:
            bool: True 表示所有规则通过，False 表示至少一个规则失败
        """
        print("🔍 ast-grep 代码质量检查")
        print("=" * 50)

        # 确定要检查的规则
        if rule_ids is None:
            rules_to_check = list(self.RULES.values())
        else:
            # 检查无效的规则 ID
            invalid_rules = set(rule_ids) - set(self.RULES.keys())
            if invalid_rules:
                print(f"⚠️  警告: 忽略无效规则 ID: {', '.join(invalid_rules)}")

            rules_to_check = [self.RULES[rid] for rid in rule_ids if rid in self.RULES]

        if not rules_to_check:
            print("❌ 错误: 没有找到有效的规则")
            return False

        # 执行检查
        results = []
        for rule in rules_to_check:
            result = self.check_rule(rule)
            self.format_rule_result(result)
            results.append(result)

        # 打印汇总
        self.print_summary(results)

        # 返回是否全部通过
        return all(r.passed for r in results)

    def list_rules(self) -> None:
        """列出所有可用规则"""
        print("📋 可用规则列表")
        print("=" * 50)

        for rule in self.RULES.values():
            icon = self.SEVERITY_ICONS[rule.severity]
            print(f"\n{icon} {rule.rule_id}: {rule.name}")
            print(f"   严重程度: {rule.severity}")
            print(f"   描述: {rule.description}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="AutoGLM-GUI ast-grep 代码质量检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                     # 检查所有规则
  %(prog)s --rule type-annotation  # 检查单个规则
  %(prog)s --rule type-annotation --rule no-print  # 检查多个规则
  %(prog)s --list              # 列出所有规则
        """,
    )

    parser.add_argument(
        "--rule",
        action="append",
        dest="rule_ids",
        help="检查指定规则 (可多次使用)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用规则",
    )

    args = parser.parse_args()

    # 获取项目根目录
    root_dir = Path(__file__).parent.parent
    if not (root_dir / "pyproject.toml").exists():
        print("❌ 错误: 无法找到项目根目录 (pyproject.toml)")
        sys.exit(1)

    # 创建检查器
    checker = AstGrepChecker(root_dir)

    # 列出规则
    if args.list:
        checker.list_rules()
        sys.exit(0)

    # 执行检查
    success = checker.check_all(rule_ids=args.rule_ids)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
