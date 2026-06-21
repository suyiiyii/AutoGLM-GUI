---
title: Agent 类型怎么选
sidebar_label: Agent 类型选型
sidebar_position: 2
---

# Agent 类型怎么选

初始化设备时（设置对话框里），可以选择不同的 **Agent 类型**。不同 Agent 对应不同的底层模型与解析方式，适合不同模型来源和任务难度。默认是 **GLM Agent**。

![Agent 类型与高级配置](/img/screenshots/settings-agent-types.png)

## 各类型一览

| Agent | 适用模型 | 特点 | 何时选 |
| --- | --- | --- | --- |
| **GLM Agent** | 智谱 GLM / AutoGLM-Phone | 成熟稳定，针对 GLM 优化 | 大多数任务的默认选择 |
| **MAI Agent** | 视觉模型 | 支持多张历史截图上下文，中文优化 | 需要「看历史几步」的复杂任务 |
| **General Vision Agent** | Gemini / GPT-4o 等 | 基于 Function Calling 的通用视觉 Agent | 想用通用多模态大模型（非专用手机模型） |
| **Qwen Agent** | Qwen 系列 | 适配 Qwen，偏高精度困难任务 | 用 Qwen 模型时 |
| **DroidRun Agent** | — | 基于 DroidRun 框架，需 Portal APK | 接入 DroidRun 生态时 |
| **Midscene Agent** | — | 基于 Midscene.js，需 Node.js 环境 | 接入 Midscene 视觉驱动时 |

## MAI Agent 的额外参数

选择 MAI Agent 时可配置 `history_n`：传给模型的历史截图数量（1–10，默认 3）。截图越多，模型对「我刚才做了什么」越有上下文，但 token 成本也越高。

MAI Agent 还提供流式思考输出、中文优化 Prompt、性能监控（LLM 耗时、动作统计）。

## 选型建议

- **拿不准就用 GLM Agent**：默认、稳定、覆盖大多数场景。
- **任务依赖上下文**（要参考前几屏内容）：用 MAI Agent，适当调大 `history_n`。
- **手头只有通用多模态模型**（如 Gemini / GPT-4o）：用 General Vision Agent。
- **DroidRun / Midscene** 面向特定框架集成，需要额外环境，普通用户一般用不到。

> 在哪里设置见[配置模型服务](../guide/configure-model.md)。注册的 Agent 类型由后端 `AutoGLM_GUI/agents/factory.py` 定义。
