---
id: quick-start
title: 快速开始
---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Android 设备（Android 11+ 支持完全无线配对，无需数据线）
- 已安装 ADB 并添加到系统 PATH（桌面版已内置）
- 一个 OpenAI 兼容的 API 端点

**关于设备连接**：
- **Android 11+**：支持二维码扫码配对，完全无需数据线即可连接和控制设备
- **Android 10 及更低版本**：需要先通过 USB 数据线连接并开启无线调试，之后可拔掉数据线无线使用

### 快捷运行（推荐）

**无需手动准备环境，直接安装运行：**

```bash
# 通过 pip 安装并启动
pip install autoglm-gui
autoglm-gui --base-url http://localhost:8080/v1
```

也可以使用 uvx 免安装启动，自动启动最新版（需已安装 uv，[安装教程](https://docs.astral.sh/uv/getting-started/installation/)）：

```bash
uvx autoglm-gui --base-url http://localhost:8080/v1
```

### 传统安装

```bash
# 从源码安装
git clone https://github.com/your-repo/AutoGLM-GUI.git
cd AutoGLM-GUI
uv sync

# 构建前端（必须）
uv run python scripts/build.py

# 启动服务
uv run autoglm-gui --base-url http://localhost:8080/v1
```

启动后，在浏览器中打开 http://localhost:8000 即可开始使用！
