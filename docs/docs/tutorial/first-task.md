---
title: 跑通第一个任务
sidebar_label: 跑通第一个任务
sidebar_position: 1
---

# 教程：跑通你的第一个任务

本教程带你从零走一遍完整流程：**连接一台设备 → 配置模型 → 发出第一条指令 → 看着 AI 在手机上执行**。跟着做完，你就理解了本工具的核心使用方式。

本教程假设你已经安装好 AutoGLM-GUI（桌面版双击即可，或 `pip install autoglm-gui` 后运行 `autoglm-gui`，详见[本地开发与构建](../guide/develop.md)）。启动后浏览器会打开主界面：

![主界面](/img/screenshots/home.png)

左侧是导航栏（对话 / Workflow / 历史 / 定时任务 / 日志 / 终端），中间是设备与对话区。下面我们一步步来。

## 第 1 步：连接一台设备

点击左侧设备栏底部的「**添加无线设备**」，弹出连接对话框：

![添加设备](/img/screenshots/device-add.png)

最简单的方式有两种：

- **模拟器**：如果你电脑上跑着 Android 模拟器（MuMu / 夜神 / 雷电 / BlueStacks），点对应的预设按钮会自动填好 IP 和端口，点「连接」即可。
- **真机（Android 11+）**：切到「配对设备」标签，用手机「无线调试 → 二维码配对」扫码连接，全程无需数据线。

> 各种连接方式的完整说明见[连接设备](../guide/connect-device.md)。

连接成功后，设备会出现在左侧列表里，绿点表示在线。点击设备卡片选中它。

## 第 2 步：配置模型服务

AutoGLM-GUI 本身不含模型，需要你提供一个 OpenAI 兼容的模型服务。点设备栏底部的「**设置**」打开配置对话框：

![模型配置](/img/screenshots/settings-vision.png)

上方三个预设可一键填好地址：

- **智谱 BigModel** —— 官方托管，填入你的 API Key 即可
- **ModelScope** —— 魔搭社区托管
- **自建服务** —— 指向你用 vLLM / SGLang 部署的端点

填好 **Base URL**、**API Key**、**Model Name** 后，点「测试连接」确认可用，再点「保存配置」。

> 模型、Agent 类型、决策模型等更细的配置见[配置模型服务](../guide/configure-model.md)。

## 第 3 步：发出第一条指令

回到对话页，确认顶部是「**经典模式**」（最简单的单模型模式）。在底部输入框里描述你想做的事，例如：

> 点击屏幕下方的消息按钮

按 `Cmd/Ctrl + Enter` 或点发送。

![准备发送](/img/screenshots/chat-ready.png)

## 第 4 步：看着 AI 执行

发送后，AI 开始工作：它截取手机屏幕、思考下一步、执行点击/滑动，并把每一步实时显示出来。右侧面板会同步显示手机当前画面。

![执行结果](/img/screenshots/chat-result.png)

上图里 AI 成功点击了消息按钮、进入消息页面，并给出了总结。底部的「2 steps completed」表示它用了 2 步完成。

🎉 恭喜，你已经跑通了第一个任务！

## 接下来

- 把常用任务存成一键复用的[Workflow](../guide/use-workflow.md)
- 让任务[定时自动执行](../guide/schedule-task.md)
- 任务跑偏时随时[打断](../guide/interrupt.md)
- 复杂任务试试[分层代理模式](../explanation/modes.md)
- 回顾每次执行的[历史记录](../guide/view-history.md)
