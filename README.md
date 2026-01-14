<div align="center">

<img src="https://github.com/user-attachments/assets/bbdaeb1c-b7f2-4a4b-a11a-34db4de0ba12" alt="autoglm-gui" width="150">

# AutoGLM-GUI

AutoGLM 手机助手的现代化 Web 图形界面 - 让 AI 自动化操作 Android 设备变得简单

**🆕 分层代理模式**：基于决策模型和视觉模型的双层协作架构，支持复杂任务规划与精准执行分离，适合需要多轮推理的高级任务。

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)
[![PyPI](https://img.shields.io/pypi/v/autoglm-gui)](https://pypi.org/project/autoglm-gui/)
<br/>
  <a href="https://qm.qq.com/q/J5eAs9tn0W" target="__blank">
    <strong>欢迎加入讨论交流群</strong>
  </a>

[English Documentation](README_EN.md)

</div>

## ✨ 特性

- **分层代理模式** - 🆕 决策模型 + 视觉模型双层协作架构，支持复杂任务规划与精准执行分离
- **完全无线配对** - 🆕 支持 Android 11+ 二维码扫码配对，无需数据线即可连接设备
- **多设备并发控制** - 同时管理和控制多个 Android 设备，设备间状态完全隔离
- **对话式任务管理** - 通过聊天界面控制 Android 设备
- **Workflow 工作流** - 🆕 预定义常用任务，一键快速执行，支持创建、编辑、删除和管理
- **实时屏幕预览** - 基于 scrcpy 的低延迟视频流，随时查看设备正在执行的操作
- **直接操控手机** - 在实时画面上直接点击、滑动操作，支持精准坐标转换和视觉反馈
- **零配置部署** - 支持任何 OpenAI 兼容的 LLM API
- **ADB 深度集成** - 通过 Android Debug Bridge 直接控制设备（支持 USB 和 WiFi）
- **模块化界面** - 清晰的侧边栏 + 设备面板设计，功能分离明确

## 📥 快速下载

**一键下载桌面版（免配置环境）：**

<div align="center">

| 操作系统 | 下载链接 | 说明 |
|---------|---------|------|
| 🪟 **Windows** (x64) | [📦 下载便携版 EXE](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.4.1/AutoGLM.GUI.1.4.1.exe) | 适用于 Windows 10/11，免安装 |
| 🍎 **macOS** (Apple Silicon) | [📦 下载 DMG](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.4.1/AutoGLM.GUI-1.4.1-arm64.dmg) | 适用于 M 芯片 Mac |
| 🐧 **Linux** (x64) | [📦 下载 AppImage](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.4.1/AutoGLM.GUI-1.4.1.AppImage) \| [deb](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.4.1/autoglm-gui_1.4.1_amd64.deb) \| [tar.gz](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.4.1/autoglm-gui-1.4.1.tar.gz) | 通用格式，支持主流发行版 |

</div>

**使用说明：**
- **Windows**: 下载后直接双击 `.exe` 文件运行，无需安装
- **macOS**: 下载后双击 `.dmg` 文件，拖拽到应用程序文件夹。首次打开可能需要在「系统设置 → 隐私与安全性」中允许运行
- **Linux**:
  - **AppImage**（推荐）: 下载后添加可执行权限 `chmod +x AutoGLM*.AppImage`，然后直接运行
  - **deb**: 适用于 Debian/Ubuntu 系统，使用 `sudo dpkg -i autoglm*.deb` 安装
  - **tar.gz**: 便携版，解压后运行 `./AutoGLM\ GUI/autoglm-gui`

> 💡 **提示**: 桌面版已内置所有依赖（Python、ADB 等），无需手动配置环境。首次运行时需配置模型服务 API。

**自动更新：**

AutoGLM GUI 桌面版支持自动更新功能：

- **🪟 Windows 安装版**：启动时自动检测更新，下载完成后退出时自动安装
- **🍎 macOS DMG**：启动时自动检测更新，下载完成后提示用户重启（未签名应用可能需要手动允许）
- **🐧 Linux AppImage**：启动时自动检测更新（需配合 [AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher)）
- **便携版（Windows EXE/Linux tar.gz）**：不支持自动更新，请手动下载新版本

---

**或者使用 Python 包（需要 Python 环境）：**

```bash
# 通过 pip 安装（推荐）
pip install autoglm-gui

# 或使用 uvx 免安装运行（需先安装 uv）
uvx autoglm-gui
```

## 📸 界面预览

快速跳转： [普通模式](#mode-classic) · [分层代理（增强）](#mode-layered)

### 分层代理

**分层代理（Layered Agent）** 是更“严格”的两层结构：**规划层**专注任务拆解与多轮推理，**执行层**专注观察与操作。规划层会通过工具调用（可在界面中看到每次调用与结果）来驱动执行层完成一个个原子子任务，便于边执行边调整策略，适合需要多轮交互/推理的高级任务。

<img width="939" height="851" alt="图片" src="https://github.com/user-attachments/assets/c054d998-726d-48ed-99e7-bb33581b3745" />


### 任务开始
![任务开始](https://github.com/user-attachments/assets/b8cb6fbc-ca5b-452c-bcf4-7d5863d4577a)

### 任务执行完成
![任务结束](https://github.com/user-attachments/assets/b32f2e46-5340-42f5-a0db-0033729e1605)

### 多设备控制
![多设备控制](https://github.com/user-attachments/assets/f826736f-c41f-4d64-bf54-3ca65c69068d)

## 🚀 快速开始

### 前置要求

- Android 设备（Android 11+ 支持完全无线配对，无需数据线）
- 一个 OpenAI 兼容的 API 端点（支持智谱 BigModel、ModelScope 或自建服务）

**关于设备连接**：
- **Android 11+**：支持二维码扫码配对，完全无需数据线即可连接和控制设备
- **Android 10 及更低版本**：需要先通过 USB 数据线连接并开启无线调试，之后可拔掉数据线无线使用

### 方式一：Python 包安装（推荐）

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

### 方式二：Docker 部署

AutoGLM-GUI 提供预构建的 Docker 镜像，支持 `linux/amd64` 和 `linux/arm64` 架构，适合服务器端远程控制 Android 设备的场景。

**使用 docker-compose（推荐）：**

```bash
# 1. 下载 docker-compose.yml
curl -O https://raw.githubusercontent.com/suyiiyii/AutoGLM-GUI/main/docker-compose.yml

# 2. 启动服务
docker-compose up -d

# 3. 访问 http://localhost:8000，在 Web 界面中配置模型 API
```

**或直接使用 docker run：**

```bash
# 使用 host 网络模式运行（推荐）
docker run -d --network host \
  -v autoglm_config:/root/.config/autoglm \
  -v autoglm_logs:/app/logs \
  ghcr.io/suyiiyii/autoglm-gui:main

# 访问 http://localhost:8000，在 Web 界面中配置模型 API
```

**配置说明**：
- 默认使用 host 网络模式（推荐，便于 ADB 设备发现和二维码配对）
- 模型 API 配置可以在 Web 界面的设置页面中完成，无需提前配置环境变量
- 如果需要在启动时预配置，可以编辑 `docker-compose.yml` 取消注释 `environment` 部分

**连接远程设备**：

Docker 容器中连接 Android 设备推荐使用 **WiFi 调试**：

1. 在 Android 设备上开启「开发者选项」→「无线调试」
2. 记录设备的 IP 地址和端口号
3. 在 Web 界面点击「添加无线设备」→ 输入 IP:端口 → 连接

> ⚠️ **注意**：二维码配对功能依赖 mDNS 多播，在 Docker bridge 网络中可能受限。**强烈建议使用 `--network host` 模式**以获得完整功能支持。

**更多 Docker 配置选项**，请参见下方的 [Docker 部署详细说明](#-docker-部署详细说明)。

---

启动后，在浏览器中打开 http://localhost:8000 即可开始使用！

### 🎯 模型服务配置

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

## 🔄 升级指南

### 检查当前版本

```bash
# 查看已安装的版本
pip show autoglm-gui

# 或使用命令行参数
autoglm-gui --version
```

### 升级到最新版本

**使用 pip 升级：**

```bash
# 升级到最新版本
pip install --upgrade autoglm-gui
```

## 📖 使用说明

### 多设备管理

AutoGLM-GUI 支持同时控制多个 Android 设备：

1. **设备列表** - 左侧边栏自动显示所有已连接的 ADB 设备
2. **设备选择** - 点击设备卡片切换到对应的控制面板
3. **状态指示** - 清晰显示每个设备的在线状态和初始化状态
4. **状态隔离** - 每个设备有独立的对话历史、配置和视频流

**设备状态说明**：
- 🟢 绿点：设备在线
- ⚪ 灰点：设备离线
- ✓ 标记：设备已初始化

#### 📱 二维码无线配对（Android 11+ 推荐）

**完全无需数据线**，手机和电脑只需在同一 WiFi 网络即可：

1. **手机端准备**：
   - 打开「设置」→「开发者选项」→ 开启「无线调试」
   - 保持手机和电脑连接到同一个 WiFi 网络

2. **电脑端操作**：
   - 点击界面左下角的 ➕ 「添加无线设备」按钮
   - 切换到「配对设备」标签页
   - **二维码自动生成**，等待扫码

3. **手机端扫码**：
   - 在「无线调试」页面，点击「使用二维码配对设备」
   - 扫描电脑上显示的二维码
   - 配对成功后，设备会自动出现在设备列表中

**特点**：
- ✅ 完全无需数据线
- ✅ 一键扫码即可配对
- ✅ 自动发现并连接设备
- ✅ 适用于 Android 11 及以上版本

### AI 自动化模式

1. **连接设备** - 使用上述任一方式连接设备（推荐 Android 11+ 的二维码配对）
2. **选择设备** - 在左侧边栏选择要控制的设备
3. **初始化** - 点击"初始化设备"按钮配置 Agent
4. **对话** - 描述你想要做什么（例如："去美团点一杯霸王茶姬的伯牙绝弦"）
5. **观察** - Agent 会逐步执行操作，每一步的思考过程和动作都会实时显示

### 🤖 选择 Agent 类型

在初始化设备时，可以选择不同的 Agent 类型（默认：GLM Agent）：

- **GLM Agent**：基于 GLM 模型优化，成熟稳定，适合大多数任务
- **MAI Agent**：**内部实现**的 Mobile Agent，支持多张历史截图上下文，适合复杂任务
  - 🆕 **现已完全内部化**：移除 ~1200 行第三方依赖，性能优化，中文适配
  - 🔄 **向后兼容**：需要使用旧版本可选择 `mai_legacy` 类型

MAI Agent 可配置参数：
- `history_n`：历史截图数量（1-10，默认：3）

**MAI Agent 增强特性**（v1.5.0+）：
- ✅ 流式思考输出（实时显示推理过程）
- ✅ 中文优化 Prompt（针对国内应用场景）
- ✅ 性能监控（LLM 耗时、动作执行统计）
- ✅ 详细的操作指南和错误避免提示

<a id="mode-classic"></a>
### 🌿 普通模式（单模型 / Open AutoGLM）

这是**开源 AutoGLM-Phone 的“原生形态”**：由一个视觉模型直接完成「理解任务 → 规划步骤 → 观察屏幕 → 执行动作」的完整闭环。

- **优点**：配置最简单，上手最快
- **适用场景**：目标明确、步骤较少的任务（例如打开应用、简单导航）

<a id="mode-layered"></a>
### 🧩 分层代理模式（Layered Agent，增强 / 实验性）

分层代理模式是更“严格”的两层结构：**规划层**专注拆解与推理，**执行层**专注观察与操作，二者通过工具调用协作完成任务。

- **工作方式**：规划层（决策模型）会调用工具（如 `list_devices()` / `chat(device_id, message)`）去驱动执行层；你能在界面里看到每次工具调用与返回结果
- **执行粒度**：执行层每次只做一个“原子子任务”，并有步数上限（例如每次最多 5 步），便于规划层按反馈动态调整策略
- **适用场景**：需要多轮推理、需要“边看边问边改计划”的复杂任务（例如浏览/筛选/对比、多轮表单填写等）
- **重要限制**：执行层不负责“记笔记/保存中间信息/直接提取文本变量”；规划层需要信息时必须通过提问让执行层把屏幕内容“念出来”

### 🎭 两种工作模式对比

AutoGLM-GUI 提供了两种不同的代理工作模式，适用于不同的使用场景：

#### 1️⃣ 经典模式（Classic Mode）
- **架构**：单一 `autoglm-phone` 视觉模型直接处理（即普通 Open AutoGLM 的体验）
- **适用场景**：简单、明确的任务
- **特点**：配置简单，适合快速上手

#### 2️⃣ 分层代理（Layered Agent）
- **架构**：基于 Agent SDK 的分层任务执行系统
  - **规划层**：决策模型作为高级智能中枢，负责任务拆解和多轮推理
  - **执行层**：autoglm-phone 作为执行者，只负责观察和操作
- **适用场景**：需要多轮交互和复杂推理的高级任务
- **特点**：规划层通过工具调用驱动执行层，过程更透明、更便于调试与迭代策略

**选择建议**：
- 🚀 **常规任务（订外卖、打车）**：经典模式
- 🏗️ **需要多轮推理的任务**：分层代理模式

### 手动控制模式

除了 AI 自动化，你也可以直接在实时画面上操控手机：

1. **实时画面** - 设备面板右侧显示手机屏幕的实时视频流（基于 scrcpy）
2. **点击操作** - 直接点击画面中的任意位置，操作会立即发送到手机
3. **滑动手势** - 按住鼠标拖动实现滑动操作（支持滚轮滚动）
4. **视觉反馈** - 每次操作都会显示涟漪动画和成功/失败提示
5. **精准转换** - 自动处理屏幕缩放和坐标转换，确保操作位置准确
6. **显示模式** - 支持自动、视频流、截图三种显示模式切换

### Workflow 工作流管理

将常用任务保存为 Workflow，实现一键快速执行：

#### 创建和管理 Workflow

1. **进入管理页面** - 点击左侧导航栏的 Workflows 图标（📋）
2. **新建 Workflow** - 点击右上角"新建 Workflow"按钮
3. **填写信息**：
   - **名称**：给 Workflow 起一个简短易记的名称（如："订购霸王茶姬"）
   - **任务内容**：详细描述要执行的任务（如："去美团点一杯霸王茶姬的伯牙绝弦，要去冰，加珍珠"）
4. **保存** - 点击保存按钮即可

**管理操作**：
- **编辑** - 点击 Workflow 卡片上的"编辑"按钮修改内容
- **删除** - 点击"删除"按钮移除不需要的 Workflow
- **预览** - Workflow 卡片显示任务内容的前几行预览

#### 快速执行 Workflow

在 Chat 界面执行已保存的 Workflow：

1. **选择设备** - 确保已选择并初始化目标设备
2. **打开 Workflow 选择器** - 点击输入框旁边的 Workflow 按钮（📋 图标）
3. **选择要执行的任务** - 从列表中点击你想执行的 Workflow
4. **自动填充** - 任务内容会自动填入输入框
5. **发送执行** - 点击发送按钮开始执行

**使用场景示例**：
- 📱 **日常任务**：订外卖、打车、查快递
- 🎮 **游戏操作**：每日签到、领取奖励
- 📧 **消息发送**：固定内容的消息群发
- 🔄 **重复操作**：定期执行的维护任务



## 🛠️ 开发指南

### 源码安装

如果你需要从源码进行开发或定制，可以按照以下步骤：

```bash
# 1. 克隆仓库
git clone https://github.com/suyiiyii/AutoGLM-GUI.git
cd AutoGLM-GUI

# 2. 安装依赖
uv sync

# 3. 构建前端（必须）
uv run python scripts/build.py

# 4. 启动服务
uv run autoglm-gui --base-url http://localhost:8080/v1
```

### 快速开发

```bash
# 后端开发（自动重载）
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload

# 前端开发服务器（热重载）
cd frontend && pnpm dev
```

### 构建和打包

```bash
# 仅构建前端
uv run python scripts/build.py

# 构建完整包
uv run python scripts/build.py --pack
```

## 🐳 Docker 部署详细说明

> 💡 **提示**：Docker 部署已整合到 [快速开始](#-快速开始) 部分，推荐直接查看上方的"方式二：Docker 部署"说明。

本节提供更多 Docker 配置选项和高级用法。

### 指定监听端口

如果使用 host 网络模式且需要修改默认端口（8000），可以通过 `command` 参数指定：

```bash
# 监听 9000 端口
docker run -d --network host \
  -v autoglm_config:/root/.config/autoglm \
  -v autoglm_logs:/app/logs \
  ghcr.io/suyiiyii/autoglm-gui:main \
  autoglm-gui --host 0.0.0.0 --port 9000 --no-browser
```

如果使用 bridge 网络模式，则使用 `-p` 参数映射端口：

```bash
# 映射主机 9000 端口到容器 8000 端口
docker run -d -p 9000:8000 \
  -v autoglm_config:/root/.config/autoglm \
  -v autoglm_logs:/app/logs \
  ghcr.io/suyiiyii/autoglm-gui:main
```

### 镜像标签

| 标签 | 说明 |
|------|------|
| `main` | 跟随 main 分支最新代码，推荐使用 |
| `<commit-sha>` | 特定 commit 的镜像（如 `abc1234`），用于锁定版本 |

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AUTOGLM_BASE_URL` | 模型 API 地址 | (必填) |
| `AUTOGLM_MODEL_NAME` | 模型名称 | `autoglm-phone` |
| `AUTOGLM_API_KEY` | API 密钥 | (必填) |

### 健康检查

```bash
# 检查服务状态
curl http://localhost:8000/api/health
```

## 🤝 如何贡献

我们热烈欢迎社区贡献！无论是修复 bug、添加新功能、改进文档，还是分享使用经验，都对项目有重要价值。

### 🎯 快速开始贡献

1. **查看置顶 Issue** - [🎯 Start Here: 如何贡献 / 认领任务 / 本地跑起来](https://github.com/suyiiyii/AutoGLM-GUI/issues/170)
2. **阅读贡献指南** - 详细步骤请参考 [CONTRIBUTING.md](./CONTRIBUTING.md)
3. **认领任务** - 在感兴趣的 Issue 下评论 `/assign me`

### 💡 贡献方式

- 🐛 **修复 Bug** - 查找标记为 `bug` 的 Issue
- ✨ **添加功能** - 实现标记为 `enhancement` 的需求
- 📖 **改进文档** - 修正错误、补充说明、添加示例
- 🧪 **添加测试** - 提升代码质量和测试覆盖率
- 🌍 **翻译文档** - 帮助更多语言的用户使用

### 🏷️ 新手友好任务

如果你是第一次贡献开源项目，可以从这些任务开始：

- 查找标记为 [`good first issue`](https://github.com/suyiiyii/AutoGLM-GUI/labels/good%20first%20issue) 的 Issue
- 改进文档（修正拼写错误、补充说明）
- 测试软件并报告使用体验

### 📚 参考资源

| 文档 | 说明 |
|------|------|
| [CONTRIBUTING.md](./CONTRIBUTING.md) | 完整的贡献指南（环境配置、开发流程、PR 规范） |
| [CLAUDE.md](./CLAUDE.md) | 技术架构文档（代码结构、关键实现细节） |
| [Issues](https://github.com/suyiiyii/AutoGLM-GUI/issues) | 查看和认领任务 |

### 💬 交流讨论

- 💭 在 Issue 中讨论想法和问题
- 🎮 加入 [QQ 交流群](https://qm.qq.com/q/J5eAs9tn0W)
- 📝 [创建新 Issue](https://github.com/suyiiyii/AutoGLM-GUI/issues/new/choose) 报告问题或提出建议

感谢每一位贡献者，你们让 AutoGLM-GUI 变得更好！🎉

## 📝 开源协议

Apache License 2.0


### 许可证说明

AutoGLM-GUI 打包了 ADB Keyboard APK (`com.android.adbkeyboard`)，该组件使用 GPL-2.0 许可证。ADB Keyboard 组件作为独立工具使用，不影响 AutoGLM-GUI 本身的 Apache 2.0 许可。

详见：`AutoGLM_GUI/resources/apks/ADBKeyBoard.LICENSE.txt`

## 🙏 致谢

本项目基于 [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 构建，感谢 zai-org 团队在 AutoGLM 上的卓越工作。
