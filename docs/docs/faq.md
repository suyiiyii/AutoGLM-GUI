---
title: 常见问题（FAQ）
sidebar_position: 50
---

# 常见问题（FAQ）

## 用 AutoGLM-GUI 需要准备什么？

一台 Android 设备（或模拟器）和一个 OpenAI 兼容的模型服务（智谱 BigModel、ModelScope 或自建 vLLM/SGLang）。桌面版已内置 Python、ADB 等依赖，无需手动配置环境。详见[跑通第一个任务](./tutorial/first-task.md)。

## 连接设备一定要数据线吗？

不一定。Android 11+ 支持二维码无线配对，全程无需数据线；Android 10 及更低版本需先用数据线开启无线调试，之后可拔线无线使用。各种连接方式见[连接设备](./guide/connect-device.md)。

## 经典模式和分层代理模式有什么区别？

经典模式是单个视觉模型直接执行，配置简单、适合步骤少的任务；分层代理把「规划」和「执行」分成两层，适合需要多轮推理的复杂任务。详见[两种工作模式](./explanation/modes.md)。

## 应该选哪个 Agent 类型？

拿不准就用默认的 GLM Agent。需要参考历史几屏的复杂任务用 MAI Agent；想用 Gemini/GPT-4o 等通用多模态模型用 General Vision Agent。详见[Agent 类型怎么选](./explanation/agent-types.md)。

## 任务执行卡住或跑偏怎么办？

任务运行时点击停止按钮即可在 1 秒内中断，然后重置对话重新开始。见[打断执行](./guide/interrupt.md)。

## 任务为什么报 ELEMENT_NOT_FOUND？

这是 Fail-Fast 策略：找不到目标元素时立即报错而不是瞎猜坐标。通常是当前屏幕和任务描述不匹配，调整指令或先手动导航到正确页面再试。更多见[排查常见问题](./guide/troubleshooting.md)。

## 历史记录存在哪里？

默认在 `~/.config/autoglm/history/`，每台设备一个 JSON 文件。Docker 部署时通过挂载 `/root/.config/autoglm` 卷持久化。查看方式见[查看对话历史](./guide/view-history.md)。

## 如何让任务自动定时执行？

先把任务存成 [Workflow](./guide/use-workflow.md)，再[创建定时任务](./guide/schedule-task.md)用 Cron 表达式调度。配合 [Docker 部署](./guide/deploy-docker.md)到服务器即可 7x24 自动运行。

## 实时画面为什么是黑的 / 不显示？

实时视频流（基于 WebCodecs/H264）在非 `localhost` 访问时需要 HTTPS，否则会回退到图像刷新模式。对外部署请配置 HTTPS，见[服务器部署](./guide/deploy-server.md)。

## Web 版能查看日志吗？

日志页是桌面版（Electron）专属。Web/Docker 部署下请查看 `logs/` 目录下的日志文件或用 `docker logs`，详见[查看日志](./guide/logs.md)。

## 能接入 Claude Desktop / Cursor 吗？

可以。AutoGLM-GUI 内置 MCP 服务器，见[接入 MCP](./guide/mcp.md)。

## 端口 8000 被占用怎么办？

不指定 `--port` 时会自动从 8000 起寻找空闲端口；也可用 `--port` 手动指定。见 [CLI 参数](./reference/cli.md)。
