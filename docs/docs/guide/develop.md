---
title: 本地开发与构建
sidebar_label: 本地开发与构建
sidebar_position: 14
---

# 本地开发与构建

这篇文档面向想从源码运行、修改或为 AutoGLM-GUI 贡献代码的开发者，覆盖从准备环境到本地开发、检查、测试和打包的完整流程。如果你只想部署运行，看[用 Docker 部署](./deploy-docker.md)即可。

后端是 Python 项目，统一用 uv 管理依赖和运行命令；前端是 React 项目，用 pnpm 管理。下面所有 Python 命令都用 `uv run` 执行，请不要直接调用裸 `python`。

## 准备环境

开始前确认本机已经装好以下工具：

- Python 3.11 或更高版本
- Node.js 18+ 和 pnpm
- uv（Python 包管理器），安装见[官方文档](https://docs.astral.sh/uv/getting-started/installation/)
- adb（Android Debug Bridge），且已加入系统 PATH

uv 的快速安装：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## 克隆仓库并安装依赖

先把仓库拉下来：

```bash
git clone https://github.com/suyiiyii/AutoGLM-GUI.git
cd AutoGLM-GUI
```

在项目根目录安装后端依赖：

```bash
uv sync
```

进入 `frontend` 安装前端依赖：

```bash
cd frontend
pnpm install
```

## 构建前端

后端通过静态资源提供前端页面。先构建一次前端并拷贝到后端静态目录：

```bash
uv run python scripts/build.py
```

这一步会编译前端产物并放到后端能直接 serve 的位置。日常只改后端时，这步做一次就够；下面的前端热重载方式则不需要它。

## 启动开发服务器

后端开发服务器支持热重载。在项目根目录运行：

```bash
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload
```

`--base-url` 指向一个 OpenAI 兼容的 API 端点。测试时可以用智谱 BigModel 或自建服务，按需替换成你自己的地址。

前端开发同样支持热重载，单独开一个终端运行：

```bash
cd frontend
pnpm dev
```

前端开发服务器默认在 `http://localhost:3000` 启动，并自动把 API 请求代理到后端。改前端时用这个，改完即时生效，不必重新执行 `scripts/build.py`。

## 代码检查与类型检查

提交前先跑 lint。在项目根目录一次性检查并自动修复后端和前端的格式：

```bash
uv run python scripts/lint.py
```

只检查不修改时加 `--check-only`；只针对某一端时加 `--backend` 或 `--frontend`，可以组合使用。例如只检查后端、不做修改：

```bash
uv run python scripts/lint.py --backend --check-only
```

类型检查分两端。后端用 pyright：

```bash
uv run pyright AutoGLM_GUI/
```

前端用 pnpm：

```bash
cd frontend
pnpm type-check
```

## 运行测试

测试用 pytest，在项目根目录运行：

```bash
uv run pytest -v
```

## 打包

构建完整包（包含构建前端并打包成 wheel）：

```bash
uv run python scripts/build.py --pack
```

不带 `--pack` 时只构建前端产物，带上 `--pack` 会在此基础上额外产出可分发的 wheel。

## 下一步

源码跑通后，如果要把它部署到服务器或容器里运行，参考[用 Docker 部署](./deploy-docker.md)。
