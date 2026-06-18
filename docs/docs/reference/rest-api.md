---
title: REST API
sidebar_label: REST API
sidebar_position: 3
---

# REST API

后端基于 FastAPI，所有接口以 `/api` 为前缀。Web 前端通过这些接口工作；任何能发 HTTP 请求的程序也可调用它们做自动化集成。服务启动后，完整的交互式接口文档可在 `/docs`（Swagger UI）查看。

下面按模块列出主要端点（不含全部查询参数，以 `/docs` 为准）。

## 对话与执行

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | 同步对话（执行至完成） |
| POST | `/api/chat/stream` | 流式对话（SSE 事件流） |
| POST | `/api/chat/abort` | 中止当前对话 |
| POST | `/api/reset` | 重置 Agent 状态 |
| GET | `/api/status` | 获取设备 / Agent 状态 |

## 分层代理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/layered-agent/chat` | 提交分层代理任务 |
| POST | `/api/layered-agent/abort` | 中止 |
| POST | `/api/layered-agent/reset` | 重置 |

## 异步任务

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/task-sessions` | 创建任务会话 |
| GET | `/api/task-sessions/{session_id}` | 获取会话 |
| POST | `/api/task-sessions/{session_id}/tasks` | 提交任务 |
| GET | `/api/task-sessions/{session_id}/tasks` | 列出会话内的任务 |
| POST | `/api/task-sessions/{session_id}/reset` | 重置会话 |
| GET | `/api/tasks` | 列出任务 |
| GET | `/api/tasks/{task_id}` | 任务详情 |
| GET | `/api/tasks/{task_id}/events` | 任务事件列表 |
| GET | `/api/tasks/{task_id}/stream` | 订阅任务事件（SSE） |
| POST | `/api/tasks/{task_id}/cancel` | 取消任务 |

## 设备

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/devices` | 列出设备 |
| GET | `/api/devices/discover_mdns` | mDNS 发现 |
| POST | `/api/devices/connect_wifi` · `/disconnect_wifi` · `/pair_wifi` | WiFi 连接 / 断开 / 配对 |
| POST | `/api/devices/connect_wifi_manual` | 手动指定 IP/端口进行 WiFi 连接 |
| POST | `/api/devices/qr_pair/generate` | 生成二维码配对会话 |
| GET | `/api/devices/qr_pair/status/{session_id}` | 获取配对状态 |
| DELETE | `/api/devices/qr_pair/{session_id}` | 取消配对会话 |
| POST | `/api/devices/add_remote` · `/remove_remote` | 添加 / 移除远程设备 |
| POST | `/api/devices/discover_remote` | 发现远程服务器上的设备 |
| GET/PUT | `/api/devices/{serial}/name` | 获取 / 设置设备名 |

## 设备分组

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/device-groups` | 列出 / 创建分组 |
| PUT/DELETE | `/api/device-groups/{group_id}` | 编辑 / 删除分组 |
| PUT | `/api/device-groups/reorder` | 重排分组 |
| PUT | `/api/devices/{serial}/group` | 把设备移入分组 |

## 手动控制

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/control/tap` · `/swipe` | 点击 / 滑动 |
| POST | `/api/control/touch/down` · `/move` · `/up` | 原始触摸事件 |
| POST | `/api/screenshot` | 截图 |
| POST | `/api/video/reset` | 重置视频流 |

## Workflow

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/workflows` | 列出 / 创建 |
| GET/PUT/DELETE | `/api/workflows/{workflow_uuid}` | 获取 / 编辑 / 删除 |

## 定时任务

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/scheduled-tasks` | 列出 / 创建 |
| GET/PUT/DELETE | `/api/scheduled-tasks/{task_id}` | 获取 / 编辑 / 删除 |
| POST | `/api/scheduled-tasks/{task_id}/enable` · `/disable` | 启用 / 禁用 |

## 历史

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/history/{serialno}` | 设备历史（分页） |
| GET | `/api/history/{serialno}/{record_id}` | 单条记录详情（含消息与附件） |
| DELETE | `/api/history/{serialno}` · `/{record_id}` | 清空 / 删除单条 |

> 历史记录的截图等附件内联在 `GET /api/history/{serialno}/{record_id}` 返回的 `messages[*].attachments` 中，没有独立的 `/artifacts` 端点。

## 配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST/DELETE | `/api/config` | 读取 / 保存 / 删除配置 |
| POST | `/api/config/model-connection-check` | 测试模型连接 |

## 其他

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/version/latest` | 检查最新版本 |
| GET | `/api/metrics` | Prometheus 指标 |
| POST | `/api/terminal/sessions` | 创建终端会话 |
| GET | `/api/terminal/sessions/{session_id}` | 获取终端会话元数据 |
| DELETE | `/api/terminal/sessions/{session_id}` | 关闭终端会话 |
| WebSocket | `/api/terminal/sessions/{session_id}/stream` | 终端双向数据流 |
| — | `/mcp` | [MCP 服务端点](./mcp-tools.md) |
| — | `/socket.io` | Socket.IO 实时通道（设备状态、视频流等） |
