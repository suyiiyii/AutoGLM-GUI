---
title: Web Terminal
---

`Web Terminal` 提供一个内置在网页中的 ADB 终端，用来快速执行常见的设备调试命令。

## 功能定位

- 这是一个 **ADB 专用终端**
- 不是通用系统 Shell
- 目前只允许执行 `adb ...` 命令
- 内置命令只支持 `help`、`clear`、`exit`、`quit`

如果输入其他命令，会看到 `Only adb commands are allowed.` 提示。

## 页面入口

- 左侧导航栏：**「终端」**
- 页面标题：**`Web Terminal`**

进入页面后，前端会自动创建一个终端会话，并建立 WebSocket 连接。

## 使用前提

使用前请确认以下条件：

- 后端服务已经正常启动
- `adb` 可执行文件可用
- 至少有一台 Android 设备已经连接，或者您准备执行 `adb connect`

本地开发常见启动方式：

```bash
uv run autoglm-gui --base-url http://localhost:8080/v1 --reload
```

前端开发模式：

```bash
cd frontend
pnpm dev
```

## 基本使用

打开页面后，终端中会显示初始化提示，例如：

- `Terminal 已就绪。目前只允许执行 adb 命令`

常见命令示例：

```bash
adb devices
adb devices -l
adb connect 192.168.1.20:5555
adb -s <device_id> shell
adb -s <device_id> logcat
```

如果需要进入指定设备的 shell，建议优先使用左侧设备列表里的快捷按钮。

## 页面上的主要按钮

- **新建会话 / 重启会话**：关闭当前终端进程并重新创建一个新会话
- **清空屏幕**：只清空前端显示，不会结束后端会话
- **关闭会话**：关闭当前终端会话和后端终端进程
- **ADB Devices**：自动发送 `adb devices -l`
- **设备快捷入口**：自动发送 `adb -s <device_id> shell`
- **刷新设备**：重新读取当前设备列表

## 会话行为说明

- 每次页面打开时，默认会自动创建一个新终端会话
- 前端和后端通过 WebSocket 双向同步输入输出
- 终端窗口尺寸变化会同步到后端 PTY
- 页面会显示当前会话状态、工作目录、启动命令和 Socket 连接状态

如果终端断开，页面上的会话状态会更新为关闭或断开。

## 安全限制

当前版本有以下限制：

- 默认只允许本机访问
- 如果服务不是以本地回环地址启动，需要显式设置 `AUTOGLM_ENABLE_WEB_TERMINAL=1`
- WebSocket 连接会校验会话 token
- WebSocket 会校验 `Origin`
- 终端只允许运行 `adb` 命令

如果您把服务部署在反向代理或远程服务器后面，请不要把这个功能当成通用远程 Shell。

## 常见问题

### 打开页面后会话立即关闭

先检查：

- `adb` 是否可用
- 后端日志里是否有终端启动错误
- 当前启动方式是否正确

建议先在仓库根目录执行：

```bash
uv run adb devices
```

如果这里就失败，`Web Terminal` 也无法正常工作。

### 提示 `Only adb commands are allowed.`

这是预期行为。当前终端不是系统 Shell，只允许执行：

- `adb ...`
- `help`
- `clear`
- `exit`
- `quit`

### 提示 `Invalid terminal session token`

这通常表示：

- 页面中的旧会话已经失效
- 会话已经被关闭
- 页面状态和后端会话状态不同步

直接点击 **「重启会话」** 一般可以恢复。

### 提示 `Web terminal is disabled for non-local hosts`

说明当前服务不是按本机模式开放，而您也没有显式启用该功能。

如果您确认要在非本地地址下启用：

```bash
AUTOGLM_ENABLE_WEB_TERMINAL=1 uv run autoglm-gui --host 0.0.0.0
```

是否应该这样做，请结合您的网络暴露范围自行评估。

## 使用建议

- 日常调试优先用 `adb devices -l`
- 多设备场景优先点左侧设备快捷入口，避免手输设备 ID
- 需要长期输出时注意终端输出量，不要无限制打印大日志
- 调试结束后主动点击 **「关闭会话」**

## 当前设计边界

`Web Terminal` 目前更适合：

- 本机开发
- 本机调试设备连接
- 快速执行少量 ADB 命令

它目前不适合：

- 暴露成公网远程终端
- 作为通用服务器 Shell
- 长时间、大流量日志流式查看工具
