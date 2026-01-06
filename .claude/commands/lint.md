---
description: 严格修复所有 lint 错误，必须全部解决
allowed-tools: Bash(uv run:*)
---

## 严格要求

**必须修复所有错误和警告，不允许任何残留。**

## 执行流程

1. 运行 lint 命令查看所有问题
2. 逐个修复所有错误和警告
3. 重新运行 lint 验证
4. 如果还有错误，继续修复
5. 重复直到完全通过（0 errors, 0 warnings）

## 执行命令

```bash
uv run python scripts/lint.py
```

## 修复原则

- **不允许跳过任何错误**
- **不允许跳过任何警告**
- **必须运行到完全通过为止**
- **TypeScript 类型错误必须修复**
- **ESLint 警告必须修复**
- **Pyright 错误必须修复**
- **Ruff 问题必须修复**

## 工作流程

1. 执行 `uv run python scripts/lint.py`
2. 分析所有错误输出
3. 使用 TodoWrite 列出所有需要修复的问题
4. 逐个修复每个问题
5. 每修复一批问题后重新运行 lint
6. 继续直到 lint 完全通过

**最终目标：lint 命令输出必须显示 "0 errors, 0 warnings" 或类似的成功信息。**
