# 贡献指南 / Contributing Guide

感谢你对 AutoGLM-GUI 的关注！我们欢迎各种形式的贡献，无论是修复 bug、添加新功能、改进文档还是提出建议。

## 📋 目录

- [贡献类型](#-贡献类型)
- [快速开始](#-快速开始)
- [认领任务](#-认领任务)
- [本地开发](#-本地开发)
- [代码结构](#-代码结构)
- [提交规范](#-提交规范)
- [Pull Request 要求](#-pull-request-要求)
- [行为准则](#-行为准则)

## 🎯 贡献类型

我们欢迎以下类型的贡献：

### 🐛 修复 Bug
- 在 Issues 中查找标记为 `bug` 的问题
- 如果发现新的 bug，请先[创建 Issue](https://github.com/suyiiyii/AutoGLM-GUI/issues/new/choose) 描述问题

### ✨ 添加新功能
- 查找标记为 `enhancement` 或 `feature` 的 Issue
- 对于较大的功能，建议先创建 Issue 讨论设计方案

### 📖 改进文档
- 修复文档中的错误或不清晰的地方
- 添加使用示例和最佳实践
- 翻译文档到其他语言

### 🧪 添加测试
- 为现有功能添加单元测试
- 改进测试覆盖率
- 添加集成测试

### 🎨 UI/UX 改进
- 优化界面交互体验
- 修复前端样式问题
- 提升可访问性

## 🚀 快速开始

### 前置要求

确保你的环境中已安装：

- **Python 3.10+**
- **Node.js 18+** 和 **pnpm**
- **uv**（Python 包管理器）- [安装教程](https://docs.astral.sh/uv/getting-started/installation/)
- **ADB** (Android Debug Bridge) - 需要添加到系统 PATH

### 安装 uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 克隆仓库

```bash
git clone https://github.com/suyiiyii/AutoGLM-GUI.git
cd AutoGLM-GUI
```

## 🏷️ 认领任务

### 查找任务

1. 浏览 [Issues 页面](https://github.com/suyiiyii/AutoGLM-GUI/issues)
2. 查找带有以下标签的 Issue：
   - `good first issue` - 适合新手的任务
   - `help wanted` - 需要社区帮助的任务
   - `bug` - Bug 修复
   - `enhancement` - 功能增强

### 认领流程

在你想要处理的 Issue 下评论：
```
/assign me
```

或者：
```
I'd like to work on this
```

维护者会将 Issue 分配给你，并提供必要的指导。

### 注意事项

- 如果一个 Issue 已经有人认领（已分配给某人），请不要重复认领
- 如果你认领后 7 天内没有进展，Issue 可能会被重新开放
- 遇到困难时，及时在 Issue 中提问，我们很乐意帮助

## 💻 本地开发

### 1. 安装依赖

**后端依赖**：
```bash
# 在项目根目录
uv sync
```

**前端依赖**：
```bash
cd frontend
pnpm install
```

### 2. 启动开发服务器

**启动后端**（支持热重载）：
```bash
# 在项目根目录
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload
```

> 注意：需要一个 OpenAI 兼容的 API 端点。测试时可以使用智谱 BigModel 或自建服务。

**启动前端**（热重载）：
```bash
cd frontend
pnpm dev
```

前端开发服务器会在 `http://localhost:3000` 启动，并自动代理 API 请求到后端。

### 3. 运行 Linting

提交代码前，请运行 linting 检查：

```bash
# 在项目根目录
uv run python scripts/lint.py
```

这会检查：
- Python 代码格式（使用 ruff）
- TypeScript/React 代码格式（使用 ESLint）

### 4. 构建项目

**构建前端**：
```bash
uv run python scripts/build.py
```

**构建完整包**（包括打包为 wheel）：
```bash
uv run python scripts/build.py --pack
```

## 📁 代码结构

### 项目目录速览

```
AutoGLM-GUI/
├── AutoGLM_GUI/              # 后端 FastAPI 应用
│   ├── api/                  # API 路由模块
│   │   ├── __init__.py       # 应用工厂
│   │   ├── agents.py         # Agent 生命周期管理
│   │   ├── devices.py        # 设备管理
│   │   └── control.py        # 设备控制
│   ├── device_manager.py     # 设备发现单例
│   ├── phone_agent_manager.py # Agent 生命周期单例
│   ├── scrcpy_stream.py      # 视频流管理
│   ├── config_manager.py     # 配置管理
│   ├── logger.py             # 日志系统
│   └── adb_plus/             # ADB 扩展工具
│
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── routes/           # 页面路由
│   │   │   ├── chat.tsx      # 主聊天界面
│   │   │   └── workflows.tsx # 工作流管理
│   │   ├── components/       # React 组件
│   │   │   ├── ScrcpyPlayer.tsx  # 视频播放器
│   │   │   ├── ChatKitPanel.tsx  # 聊天面板
│   │   │   └── DevicePanel.tsx   # 设备面板
│   │   └── api.ts            # API 客户端
│   └── package.json
│
├── scripts/                  # 构建和工具脚本
│   ├── build.py              # 前端构建脚本
│   ├── lint.py               # 代码检查
│   └── build_electron.py     # Electron 打包
│
├── CLAUDE.md                 # AI 辅助开发文档（项目技术细节）
├── README.md                 # 用户文档
└── pyproject.toml            # Python 项目配置
```

### 关键入口文件

- **后端入口**: `AutoGLM_GUI/__main__.py` - CLI 入口点
- **API 应用**: `AutoGLM_GUI/api/__init__.py` - FastAPI 应用工厂
- **前端入口**: `frontend/src/main.tsx` - React 应用入口
- **路由配置**: `frontend/src/routes/__root.tsx` - 根布局和路由

### 技术栈

**后端**：
- FastAPI + Uvicorn (Web 框架)
- Socket.IO (实时通信)
- ADB (Android 设备控制)
- scrcpy (屏幕流)
- loguru (日志)

**前端**：
- React 19 + TypeScript
- TanStack Router (路由)
- Tailwind CSS 4 (样式)
- Radix UI (组件库)
- Socket.IO Client (实时通信)

## 📝 提交规范

我们遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

### Commit 格式

```
<类型>(<范围>): <简短描述>

[可选的详细描述]

[可选的脚注]
```

### 类型 (Type)

- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档变更
- `style`: 代码格式调整（不影响功能）
- `refactor`: 重构（既不是新功能也不是 bug 修复）
- `perf`: 性能优化
- `test`: 添加或修改测试
- `chore`: 构建过程或辅助工具的变动

### 范围 (Scope)

可选，指明改动的模块：
- `api` - 后端 API
- `frontend` - 前端
- `device` - 设备管理
- `agent` - Agent 相关
- `ui` - 用户界面
- `build` - 构建系统
- `docs` - 文档

### 示例

```bash
feat(api): add layered agent support
fix(frontend): fix video stream coordinate transformation
docs: update installation guide for Windows users
refactor(device): simplify device discovery logic
```

## 🔍 Pull Request 要求

### 提交前检查清单

- [ ] 代码通过 linting 检查 (`uv run python scripts/lint.py`)
- [ ] 对于新功能，添加了相应的文档说明
- [ ] 对于 UI 改动，提供了截图或录屏
- [ ] Commit 信息遵循规范格式
- [ ] PR 描述清晰说明了改动内容和原因

### PR 标题格式

PR 标题应该简洁明了，建议格式：

```
<类型>: <简短描述>
```

例如：
- `feat: add WiFi device pairing support`
- `fix: resolve video stream crash on device disconnect`
- `docs: improve quick start guide`

### PR 描述模板

提交 PR 时，请使用以下模板：

```markdown
## 改动说明

<!-- 简要描述这个 PR 做了什么 -->

## 相关 Issue

<!-- 关联的 Issue 编号，如 Closes #123 -->

## 改动类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 文档更新
- [ ] 代码重构
- [ ] 性能优化
- [ ] 其他（请说明）

## 测试说明

<!-- 如何测试这些改动？ -->

## 截图/录屏

<!-- 对于 UI 改动，请提供截图或录屏 -->

## 其他说明

<!-- 其他需要说明的内容 -->
```

### Code Review

提交 PR 后：
1. 维护者会审查你的代码
2. 可能会提出改进建议
3. 请及时回复评论并根据反馈调整代码
4. 所有讨论解决后，PR 会被合并

## 🤝 行为准则

### 我们的承诺

为了营造一个开放和友好的环境，我们承诺：

- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

### 不可接受的行为

以下行为被视为不可接受：

- 使用性别化的语言或图像，以及不受欢迎的性关注
- 骚扰性评论、侮辱性/贬损性评论，以及人身或政治攻击
- 公开或私下骚扰
- 未经明确许可，发布他人的私人信息
- 其他在专业环境中可能被认为不适当的行为

## 🎉 感谢贡献

感谢你花时间为 AutoGLM-GUI 做出贡献！你的努力让这个项目变得更好。

有任何问题？欢迎：
- 在 [Issues](https://github.com/suyiiyii/AutoGLM-GUI/issues) 提问
- 加入我们的 [QQ 交流群](https://qm.qq.com/q/J5eAs9tn0W)

---

**提示**：更多技术细节请参考 [`CLAUDE.md`](./CLAUDE.md)，这是一份面向 AI 辅助开发的技术文档，包含了完整的架构说明。
