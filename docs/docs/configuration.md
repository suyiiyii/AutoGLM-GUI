---
id: configuration
title: 模型配置
---

## 🎯 模型服务配置

AutoGLM-GUI 只需要一个 OpenAI 兼容的模型服务。你可以：

- 使用官方已托管的第三方服务
  - 智谱 BigModel：`--base-url https://open.bigmodel.cn/api/paas/v4`，`--model autoglm-phone`，`--apikey <你的 API Key>`
  - ModelScope：`--base-url https://api-inference.modelscope.cn/v1`，`--model ZhipuAI/AutoGLM-Phone-9B`，`--apikey <你的 API Key>`
- 或自建服务：参考上游项目的[部署文档](https://github.com/zai-org/Open-AutoGLM/blob/main/README.md)用 vLLM/SGLang 部署 `zai-org/AutoGLM-Phone-9B`，启动 OpenAI 兼容端口后将 `--base-url` 指向你的服务。

示例：

```bash
# 使用智谱 BigModel
pip install autoglm-gui
autoglm-gui \
  --base-url https://open.bigmodel.cn/api/paas/v4 \
  --model autoglm-phone \
  --apikey sk-xxxxx

# 使用 ModelScope
pip install autoglm-gui
autoglm-gui \
  --base-url https://api-inference.modelscope.cn/v1 \
  --model ZhipuAI/AutoGLM-Phone-9B \
  --apikey sk-xxxxx

# 指向你自建的 vLLM/SGLang 服务
pip install autoglm-gui
autoglm-gui --base-url http://localhost:8000/v1 --model autoglm-phone-9b
```

## ⏱️ 执行步数设置

AutoGLM-GUI 默认使用有限步数执行任务：

- `default_max_steps = 100`
- 在设置页可以修改为更大的数字
- **留空** 表示 **不限制步数**

### 留空后的语义

当 `default_max_steps` 留空时：

- 主执行链不再因为固定步数上限提前结束
- 任务会持续运行，直到：
  - 正常完成
  - 用户手动停止
  - 系统保护条件触发

### 使用建议

- 这是**高级设置**
- 修改后会影响后续任务默认行为，而不是只影响当前一次任务
- 如果只是验证复杂长任务，建议临时留空，验证完成后再恢复为显式数字

### 安全边界

即使 `default_max_steps` 留空，下列保护仍然存在：

- MCP / tool 层保留独立步数上限
- 用户可以手动停止任务
- 任务结束原因可观测
