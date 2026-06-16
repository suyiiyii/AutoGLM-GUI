---
title: 文档总览
slug: /
sidebar_position: 1
---

# AutoGLM-GUI 文档

AutoGLM-GUI 是一个 AI 驱动的 Android 自动化工具：你用自然语言描述任务（例如「打开微信给张三发消息」），它通过视觉模型理解屏幕、规划步骤并在手机上执行。支持桌面版、Python 包和 Docker 部署，可配合定时任务长期运行。

这套文档按你**当下想做什么**分成四类，按需取用：

## 📖 教程（第一次使用看这里）

如果你刚接触本工具，从[**跑通第一个任务**](./tutorial/first-task.md)开始。它带你从零走一遍：连接设备 → 配置模型 → 发出第一条指令 → 看到 AI 执行。

## 🛠️ 操作指南（我要完成某件具体的事）

已经上手、想解决一个具体问题时看「操作指南」。每篇是一份「菜谱」，比如[连接设备](./guide/connect-device.md)、[配置模型服务](./guide/configure-model.md)、[创建定时任务](./guide/schedule-task.md)、[Docker 部署](./guide/deploy-docker.md)、[排查常见问题](./guide/troubleshooting.md)等。

## 📋 参考（我要查一个准确的事实）

「参考」是字典式的精确清单，用来查命令、参数、接口：[CLI 命令行参数](./reference/cli.md)、[环境变量](./reference/env-vars.md)、[REST API](./reference/rest-api.md)、[MCP 工具](./reference/mcp-tools.md)、[Docker 配置](./reference/docker.md)。

## 💡 原理解释（我想搞懂它为什么这么设计）

「原理解释」讨论设计动机与取舍，帮你建立整体理解：[两种工作模式](./explanation/modes.md)、[Agent 类型怎么选](./explanation/agent-types.md)、[分层代理架构](./explanation/layered-agent.md)、[追踪与可观测性](./explanation/observability.md)。

---

> 找不到想要的内容？先看 [FAQ](./faq.md)，或到 [GitHub Issues](https://github.com/suyiiyii/AutoGLM-GUI/issues) 提问。
