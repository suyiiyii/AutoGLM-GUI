---
title: 配置模型服务
sidebar_label: 配置模型服务
sidebar_position: 2
---

# 配置模型服务

本指南带你在 AutoGLM-GUI 里完成一次完整的模型服务配置：选好视觉模型、填好连接信息、测通连接并保存。配置只需做一次，之后所有任务都会沿用这套设置。

## 打开配置对话框

在左侧设备栏底部点击「设置」，即可打开配置对话框。对话框顶部有两个标签页：「视觉模型」和「决策模型」。绝大多数场景只需要配置「视觉模型」，只有在使用分层代理时才需要额外配置「决策模型」（见下文）。

## 配置视觉模型

切到「视觉模型」标签页。

![视觉模型配置](/img/screenshots/settings-vision.png)

### 1. 选择预设配置

「选择预设配置」一栏提供三个预设，点击其中一个即可自动填好对应的 Base URL 和 Model Name：

- 智谱 BigModel：智谱 AI 提供的 API 服务。
- ModelScope：魔搭社区提供的 API 服务。
- 自建服务：vLLM / SGLang 等自建服务。

智谱 BigModel 和 ModelScope 这两个云服务预设的卡片右上角有一个外链图标，点击「获取 API Key」会跳到对应平台去申请密钥。如果你用 vLLM、SGLang 等自己部署的服务，选「自建服务」，再手动填下面的字段。

### 2. 填写连接信息

预设之下有三个字段：

- Base URL（必填）：模型服务的 OpenAI 兼容接口地址，例如 `http://localhost:8080/v1`。留空会提示「Base URL 为必填项」。
- API Key：服务需要鉴权时填写；自建服务若不需要鉴权可以留空。右侧的眼睛图标可以切换明文显示。
- Model Name：要调用的模型名，例如 `autoglm-phone-9b`。

选了预设后，这些字段会预填默认值，你可以按需修改。

### 3. 测试连接

填好后点击「测试连接」。按钮会显示「测试中...」，结束后给出「连接成功」或「连接失败」。测试需要 Base URL 和 Model Name 都已填写才能点击。先测通再保存，能避免任务运行时才发现地址或密钥写错。

### 4. 保存

确认无误后，点对话框底部的「保存配置」。保存成功会提示「配置已保存」。

## 选择 Agent 类型

在「视觉模型」标签页下方的「Agent 类型」区域，可以选择驱动任务的 Agent。不同 Agent 对应不同的模型与执行方式：

- GLM Agent：基于 GLM 模型优化，成熟稳定，适合大多数任务。
- MAI Agent：阿里通义团队开发，支持多张历史截图上下文。
- General Vision Agent：通用视觉模型，支持 Gemini/GPT-4o 等，使用 Function Calling。
- Qwen Agent：Qwen 系列适配。
- DroidRun Agent：基于 DroidRun 框架，需安装 Portal APK。
- Midscene Agent：基于 Midscene.js 视觉驱动，需要 Node.js 环境。

![Agent 类型与高级选项](/img/screenshots/settings-agent-types.png)

不确定选哪个时，先用默认的 GLM Agent。各 Agent 的差异和适用场景见[Agent 类型说明](../explanation/agent-types.md)。

## 高级选项

切换 Agent 类型时，下方会出现与之相关的高级项。这些设置会影响后续任务的默认行为，修改后可能增加执行时长与模型调用成本，按需调整即可。

历史记录数量（history_n）：仅在选中 MAI Agent 时出现，控制传给模型的历史截图数量，取值 1–10，默认 3。截图越多上下文越完整，但开销也越大。

最大执行步数：单次任务允许执行的最大步数。留空表示不限制，任务会一直运行直到手动停止。

分层代理最大轮次（layered_max_turns）：分层代理模式下规划层的最大轮次，最小值为 1。关于分层代理与经典模式的区别，见[执行模式说明](../explanation/modes.md)。

## 配置决策模型

「决策模型」标签页只在使用分层代理模式时才需要。分层代理把任务拆成规划层和执行层，决策模型负责规划层；使用该模式时必须配置决策模型。

![决策模型配置](/img/screenshots/settings-decision.png)

切到「决策模型」标签页，填法和视觉模型一致：

1. 在「选择决策模型预设」里选一个预设（智谱 BigModel / ModelScope / 自建服务），自动填好决策模型的 Base URL 和 Model Name。
2. 按需修改决策模型 Base URL、决策模型 API Key、决策模型 Model Name。
3. 点「测试连接」确认连通，再回到底部「保存配置」。

如果不打算用分层代理，这个标签页可以留空。

## 相关参考

- 各 Agent 类型详解：[Agent 类型说明](../explanation/agent-types.md)
- 经典模式与分层代理的区别：[执行模式说明](../explanation/modes.md)
- 命令行启动参数：[CLI 参考](../reference/cli.md)
- 环境变量：[环境变量参考](../reference/env-vars.md)
