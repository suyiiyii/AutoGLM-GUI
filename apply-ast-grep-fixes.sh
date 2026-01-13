#!/bin/bash
# AutoGLM-GUI ast-grep 自动应用脚本
# 功能：升级 Python 类型注解到新语法 (Python 3.10+)

set -e

echo "🔧 AutoGLM-GUI - ast-grep 自动修复工具"
echo "=========================================="
echo ""

# 检查 ast-grep 是否安装
if ! command -v sg &> /dev/null; then
    echo "❌ 错误: ast-grep 未安装"
    echo "请访问 https://ast-grep.github.io/ 安装"
    exit 1
fi

echo "✅ 检测到 ast-grep: $(sg --version | head -1)"
echo ""

# 备份提示
echo "⚠️  注意: 此脚本将修改代码，建议先提交当前更改"
echo "   创建备份: git add . && git commit -m 'backup before ast-grep fixes'"
echo ""
read -p "是否继续? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 1
fi

echo ""
echo "🚀 开始应用修复..."
echo ""

# 1. Rewrite Optional[str] to str | None
echo "📝 [1/3] 升级 Optional[str] → str | None"
sg run --lang python -p 'Optional[str]' -r AutoGLM_GUI/ --fix 'str | None' -u

# 2. Rewrite Optional[int] to int | None
echo "📝 [2/3] 升级 Optional[int] → int | None"
sg run --lang python -p 'Optional[int]' -r AutoGLM_GUI/ --fix 'int | None' -u

# 3. Rewrite Optional[dict] to dict | None
echo "📝 [3/3] 升级 Optional[dict] → dict | None"
sg run --lang python -p 'Optional[dict]' -r AutoGLM_GUI/ --fix 'dict | None' -u

echo ""
echo "✅ 修复完成!"
echo ""
echo "📋 后续步骤:"
echo "   1. 查看修改: git diff"
echo "   2. 运行测试: uv run python scripts/lint.py"
echo "   3. 提交更改: git add . && git commit -m 'refactor: upgrade type hints to PEP 604'"
echo ""
echo "📚 详细报告: AST_GREP_REPORT.md"
