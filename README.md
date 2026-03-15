<div align="center">

<img src="https://github.com/user-attachments/assets/bbdaeb1c-b7f2-4a4b-a11a-34db4de0ba12" alt="autoglm-gui" width="150">

# AutoGLM-GUI

**AI 驱动的 Android 自动化生产力工具**，借助多设备控制、定时任务和可插拔模型接口，把手机操作交给智能 Agent 24/7 执行。

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)
[![PyPI](https://img.shields.io/pypi/v/autoglm-gui)](https://pypi.org/project/autoglm-gui/)

---

**文档站**：[auto-glm-gui-docs.vercel.app](https://auto-glm-gui-docs.vercel.app) · [English overview](README_EN.md)

</div>

## 为什么是 AutoGLM-GUI

AutoGLM-GUI 把 Android 手机自动化放进一个对话式控制台：Model + scrcpy + ADB 协同工作，分层 Agent 架构让复杂任务也能稳定执行。你可以在 Web/桌面界面里调度工作流、观看视频流、关联定时任务，或把它部署到 Docker/服务器上全天候运行。

## 核心特性

- **分层 Agent + 多模型协作**：规划层负责拆解、执行层负责观察，两个模型可以同时并行，适合复杂路径和多轮管控。
- **多设备与分组管理**：同时管理多台设备，设备状态互不影响，支持卡片式操作与分组策略。
- **定时任务与 Workflow**：内置 Cron 式调度；把常用流程保存成 Workflow，一键复用或通过 API 调用。
- **实时屏幕与直接操控**：基于 scrcpy 实现低延迟视频流，界面上直接点/滑/输即可控制设备。
- **Docker & 服务器部署**：官方 Docker 镜像覆盖 x64/ARM64，推荐 `--network host` 以保留二维码配对能力。
- **深度 ADB 与 MCP 集成**：WiFi/USB 双模控制、无限接入、内置 MCP 接口可供 Claude、Cursor 等接入。

## 选择你的路径

1. **桌面用户**：下载桌面版/运行 Python 包，按照 [文档站 “开始使用”](https://auto-glm-gui-docs.vercel.app/docs/getting-started/install) 指南完成初次运行、模型配置与设备连接。
2. **部署用户**：参考 [部署 > Docker](https://auto-glm-gui-docs.vercel.app/docs/deployment/docker) 和 [部署 > 服务器](https://auto-glm-gui-docs.vercel.app/docs/deployment/server)，在服务器上 24/7 启动 AutoGLM-GUI，并利用定时任务自动触发 Workflow。
3. **贡献者**：先读 [`CONTRIBUTING.md`](./CONTRIBUTING.md)，在 `uv sync` 后用 `uv run autoglm-gui --reload` 和 `pnpm dev` 本地联调，再提交符合 Conventional Commits 的改动。

## 快速安装

```bash
# 推荐：通过 PyPI 安装并启动
pip install autoglm-gui
autoglm-gui --base-url http://localhost:8080/v1

# 或者使用 uvx（需要先装 uv）
uvx autoglm-gui --base-url http://localhost:8080/v1
```

## 界面预览

![Layered Agent UI](https://github.com/user-attachments/assets/c054d998-726d-48ed-99e7-bb33581b3745)

## 继续阅读

- [完整用户指南 / 文档站](https://auto-glm-gui-docs.vercel.app/docs/intro)
- [贡献流程](./CONTRIBUTING.md) 与 [issues](https://github.com/suyiiyii/AutoGLM-GUI/issues)
- [Release notes](https://auto-glm-gui-docs.vercel.app/docs/release-notes-v-1-5)（仅保留重要节点）
- [模型配置说明](https://auto-glm-gui-docs.vercel.app/docs/getting-started/model-config) 以配置 OpenAI 兼容服务

欢迎继续通过文档站、Issues 和社区交流群了解更多。
