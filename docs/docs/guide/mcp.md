---
title: 接入 MCP
sidebar_label: 接入 MCP
sidebar_position: 11
---

# 把 AutoGLM-GUI 接入 Claude Desktop / Cursor / Cline

本指南教你把 AutoGLM-GUI 作为一个 MCP 服务器接入 Claude Desktop、Cursor、Cline 等支持 MCP 的 AI 应用，让这些 AI 直接调用工具操控你的安卓设备。

## 什么是 MCP，能干什么

MCP（Model Context Protocol）是一个开放协议，让 AI 应用连接到外部工具和数据源。AutoGLM-GUI 内置了一个 MCP 服务器，接入之后，AI 应用就能在对话里直接调用 AutoGLM-GUI 暴露的工具：列出连接的设备、截屏、把一句自然语言任务下发给手机 Agent 执行、提交并轮询异步任务等。

换句话说，你在 Claude Desktop 里说一句「在模拟器上打开设置应用」，Claude 就会调用 AutoGLM-GUI 的工具，由手机 Agent 在真实设备上完成这步操作，再把结果返回给你。

整个过程依赖一个正常运行的 AutoGLM-GUI 后端，AI 应用通过 HTTP 连接到它的 `/mcp` 端点。

## 第一步：启动 AutoGLM-GUI，确保 /mcp 端点可访问

MCP 服务器和主服务跑在同一个进程、同一个端口（默认 8000），随后端一起启动，无需单独开启。

正常启动后端：

```bash
autoglm-gui --base-url http://localhost:8080/v1
```

启动后，MCP 端点挂载在 `/mcp` 路径下，完整地址为：

```
http://localhost:8000/mcp
```

传输方式是 HTTP（Streamable HTTP / SSE）。你可以用一条请求确认端点存活（返回非连接错误即说明服务在监听）：

```bash
curl -i http://localhost:8000/mcp
```

如果你改了主服务端口，MCP 端点会跟随同一个端口，记得在后面的客户端配置里把 URL 一并改掉。

## 第二步：配置 Claude Desktop

先找到 Claude Desktop 的配置文件：

- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows：`%APPDATA%\Claude\claude_desktop_config.json`

在文件里加入 `mcpServers` 配置（如果文件已有别的内容，把 `autoglm-gui` 这一项合并进 `mcpServers` 即可）：

```json
{
  "mcpServers": {
    "autoglm-gui": {
      "transport": {
        "type": "http",
        "url": "http://localhost:8000/mcp"
      }
    }
  }
}
```

保存后重启 Claude Desktop。重启后，AutoGLM-GUI 的工具就会出现在对话中，Claude 可以按需调用。

## 第三步：配置 Cline 和 Cursor

### Cline（VS Code 插件）

在 VS Code 设置中搜索 `cline`，添加 MCP 服务器配置：

```json
{
  "cline.mcpServers": {
    "autoglm-gui": {
      "transport": {
        "type": "http",
        "url": "http://localhost:8000/mcp"
      }
    }
  }
}
```

### Cursor

打开 Cursor 的设置，进入 MCP Servers，添加：

```json
{
  "mcpServers": {
    "autoglm-gui": "http://localhost:8000/mcp"
  }
}
```

三个客户端连的都是同一个 `http://localhost:8000/mcp` 端点，区别只在各自的配置写法。

## 第四步：了解可用的工具

接入成功后，AI 应用能调用以下工具，可大致分为三类：

设备相关：`list_devices` 列出所有连接的设备及其状态，`get_device` 查询单台设备详情，`screenshot` 对指定设备截屏（只读，不影响 Agent 执行）。

同步执行：`chat` 把一句自然语言任务下发给手机 Agent 同步执行。它使用专门的 Fail-Fast 提示词，面向 5 步内可完成的原子操作；找不到元素会立即报错而不是猜坐标，超过步数上限会自动中断。

异步任务：`create_task` 把任务提交到设备的任务队列异步执行，`get_task` 查任务状态和结果，`list_tasks` 按条件列任务，`get_task_events` 拉取逐步执行事件，`cancel_task` 取消排队或运行中的任务。

每个工具的参数、返回结构和错误码，见 [MCP 工具参考](../reference/mcp-tools.md)。如果你想绕过 MCP、直接用 HTTP 调后端，可参考 [REST API 参考](../reference/rest-api.md)。

## 最佳实践

任务保持原子化。`chat` 工具被设计为执行 5 步内能完成的原子操作，复杂流程要拆成多个子任务依次下发。一旦返回提示「已达到最大步数限制」，说明这一步太大，应该拆细后重试。

先 list_devices 再操作。下发任何动作前，先调用 `list_devices` 确认目标设备在线，并拿到准确的 `device_id`（异步任务还需要 `device_serial`）。设备离线或 ID 写错会直接导致调用失败。

捕获 ELEMENT_NOT_FOUND。Fail-Fast 提示词在找不到目标元素时会返回 `ELEMENT_NOT_FOUND`。AI 端应当捕获这个错误，而不是继续盲目重试同一步；正确做法是先截屏看清当前界面，调整策略后再下发新指令。
