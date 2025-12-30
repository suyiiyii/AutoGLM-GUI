<div align="center">

<img src="https://github.com/user-attachments/assets/bbdaeb1c-b7f2-4a4b-a11a-34db4de0ba12" alt="autoglm-gui" width="150">

# AutoGLM-GUI

AutoGLM 手机助手的现代化 Web 图形界面 - 让 AI 自动化操作 Android 设备变得简单

**🎉 Android 11+ 设备现已支持完全无线连接，扫码即配对，无需数据线！🎉**

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

- **🧠 双模型协作** - 🆕 决策大模型 + 视觉小模型协作架构，智能任务规划与精准执行分离，支持三种工作模式（DEEP/FAST/TURBO）
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
| 🪟 **Windows** (x64) | [📦 下载便携版 EXE](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.3.0/AutoGLM.GUI.1.3.0.exe) | 适用于 Windows 10/11，免安装 |
| 🍎 **macOS** (Apple Silicon) | [📦 下载 DMG](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.3.0/AutoGLM.GUI-1.3.0-arm64.dmg) | 适用于 M 芯片 Mac |
| 🐧 **Linux** (x64) | [📦 下载 AppImage](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.3.0/AutoGLM.GUI-1.3.0.AppImage) \| [deb](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.3.0/autoglm-gui_1.3.0_amd64.deb) \| [tar.gz](https://github.com/suyiiyii/AutoGLM-GUI/releases/download/v1.3.0/autoglm-gui-1.3.0.tar.gz) | 通用格式，支持主流发行版 |

</div>

**使用说明：**
- **Windows**: 下载后直接双击 `.exe` 文件运行，无需安装
- **macOS**: 下载后双击 `.dmg` 文件，拖拽到应用程序文件夹。首次打开可能需要在「系统设置 → 隐私与安全性」中允许运行
- **Linux**:
  - **AppImage**（推荐）: 下载后添加可执行权限 `chmod +x AutoGLM*.AppImage`，然后直接运行
  - **deb**: 适用于 Debian/Ubuntu 系统，使用 `sudo dpkg -i autoglm*.deb` 安装
  - **tar.gz**: 便携版，解压后运行 `./AutoGLM\ GUI/autoglm-gui`

> 💡 **提示**: 桌面版已内置所有依赖（Python、ADB 等），无需手动配置环境。首次运行时需配置模型服务 API。

---

**或者使用 Python 包（需要 Python 环境）：**

```bash
# 通过 pip 安装（推荐）
pip install autoglm-gui

# 或使用 uvx 免安装运行（需先安装 uv）
uvx autoglm-gui
```

## 📸 界面预览

### 双模型架构
决策模型+视觉模型 双模型架构，更好的执行复杂任务
<img width="879" height="849" alt="图片" src="https://github.com/user-attachments/assets/15e5cf51-5a19-403d-9af3-46f77c2068f5" />

### 任务开始
![任务开始](https://github.com/user-attachments/assets/b8cb6fbc-ca5b-452c-bcf4-7d5863d4577a)

### 任务执行完成
![任务结束](https://github.com/user-attachments/assets/b32f2e46-5340-42f5-a0db-0033729e1605)

### 多设备控制
![多设备控制](https://github.com/user-attachments/assets/f826736f-c41f-4d64-bf54-3ca65c69068d)

## 🚀 快速开始

## 🎯 模型服务配置

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

### 快速开发

```bash
# 后端开发（自动重载）
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload

# 前端开发服务器（热重载）
cd frontend && pnpm dev

### 构建和打包

```bash
# 仅构建前端
uv run python scripts/build.py

# 构建完整包
uv run python scripts/build.py --pack
```

## 📝 开源协议

Apache License 2.0


### 许可证说明

AutoGLM-GUI 打包了 ADB Keyboard APK (`com.android.adbkeyboard`)，该组件使用 GPL-2.0 许可证。ADB Keyboard 组件作为独立工具使用，不影响 AutoGLM-GUI 本身的 MIT 许可。

详见：`AutoGLM_GUI/resources/apks/ADBKeyBoard.LICENSE.txt`

## 🙏 致谢

本项目基于 [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 构建，感谢 zai-org 团队在 AutoGLM 上的卓越工作。
