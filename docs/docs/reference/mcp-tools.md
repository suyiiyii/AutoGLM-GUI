---
title: MCP 工具
sidebar_label: MCP 工具
sidebar_position: 4
---

# MCP 工具

AutoGLM-GUI 内置一个 [MCP](https://modelcontextprotocol.io/)（Model Context Protocol）服务器，挂载在 `/mcp` 路径上（HTTP + SSE 传输）。Claude Desktop、Cursor、Cline 等支持 MCP 的应用接入后，即可让它们的 AI 直接操控你的 Android 设备。接入配置见[接入 MCP](../guide/mcp.md)。

MCP 服务器暴露以下工具。

## 设备

### `list_devices()`

列出所有已连接的 ADB 设备及其状态。

- **参数**：无
- **返回**：设备列表（设备 ID、型号、连接类型、在线状态、Agent 初始化状态）

### `get_device(device_id)`

按 `device_id` 获取单个设备详情。

- **参数**：`device_id`（字符串）
- **返回**：设备详情；不存在时返回 `null`

### `screenshot(device_id)`

截取指定设备当前屏幕（只读操作，不改变设备状态）。

- **参数**：`device_id`（字符串）
- **返回**：截图数据（含尺寸）

## 同步执行

### `chat(device_id, message)`

向指定设备发送一个任务并**同步执行**，适合原子操作。

- **参数**：`device_id`（字符串）、`message`（自然语言任务描述）
- **返回**：`ChatResult`（`result` 结果文本、`steps` 步数、`success` 是否成功）
- **行为约束**：
  - **Fail-Fast**：找不到目标元素立即报错（`ELEMENT_NOT_FOUND`），不猜测坐标
  - **5 步上限**：超过自动中断（`STEP_LIMIT_EXCEEDED`），避免无限循环

> 复杂任务应拆成多个原子 `chat` 调用，或改用下面的异步任务接口。

## 异步任务

适合长任务：提交后立即返回 `task_id`，再轮询状态或拉取事件。

### `create_task(device_id, device_serial, message, mode="classic")`

提交一个异步任务到设备队列。

- **参数**：`device_id`、`device_serial`、`message`、`mode`（`classic` 或 `layered`）
- **返回**：`{task_id, session_id, status, input_text}`

### `get_task(task_id)`

获取任务当前状态与结果。返回任务对象；不存在时返回 `null`。

### `list_tasks(status=None, device_id=None, device_serial=None, limit=20, offset=0)`

列出任务，支持按状态/设备过滤、分页（`limit` 取值 1–100）。返回 `{tasks, total, limit, offset}`。

### `cancel_task(task_id)`

取消排队中或运行中的任务。返回 `{success, message, task}`。

### `get_task_events(task_id, after_seq=0)`

获取任务的步骤级执行事件（用于展示进度）。返回 `{task_id, events}`。

## 端点

| 项 | 值 |
| --- | --- |
| 基础路径 | `http://<host>:<port>/mcp` |
| 传输 | HTTP + SSE |
| 端口 | 跟随主服务端口（默认 8000） |

> REST 形式的等价接口见 [REST API](./rest-api.md)。
