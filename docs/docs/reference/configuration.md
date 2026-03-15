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
