---
title: 环境变量
sidebar_label: 环境变量
sidebar_position: 2
---

# 环境变量

除了[命令行参数](./cli.md)和 Web 界面配置，AutoGLM-GUI 也读取以下环境变量。环境变量在 Docker 部署、CI 等场景下尤其方便（在 `docker-compose.yml` 的 `environment` 段设置即可）。

## 模型服务

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTOGLM_BASE_URL` | 无 | 模型 API 基础地址（必填其一：此处或界面配置） |
| `AUTOGLM_MODEL_NAME` | `autoglm-phone-9b` | 模型名称 |
| `AUTOGLM_API_KEY` | `EMPTY` | 模型 API 密钥 |

## 决策模型（分层代理用）

[分层代理模式](../explanation/layered-agent.md)的规划层使用一个独立的「决策模型」。不配置时回退到上面的主模型。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTOGLM_DECISION_BASE_URL` | 无 | 决策模型 API 基础地址 |
| `AUTOGLM_DECISION_MODEL_NAME` | 无 | 决策模型名称 |
| `AUTOGLM_DECISION_API_KEY` | 无 | 决策模型 API 密钥 |

## 执行控制

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTOGLM_DEFAULT_MAX_STEPS` | `100` | 经典模式单次任务的最大步数 |
| `AUTOGLM_LAYERED_MAX_TURNS` | `50` | 分层代理模式的最大轮数 |

## 服务与日志

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTOGLM_CORS_ORIGINS` | `http://localhost:3000` | 允许的 CORS 来源 |
| `AUTOGLM_ENABLE_WEB_TERMINAL` | `0` | 置为 `1` 启用 [Web 终端](../guide/web-terminal.md) |
| `AUTOGLM_SERVER_HOST` | `127.0.0.1` | 服务绑定的主机地址，Web 终端等内部模块使用 |
| `AUTOGLM_ADB_PATH` | `adb` | adb 可执行文件路径 |
| `AUTOGLM_LOG_LEVEL` | `INFO` | 日志级别（`--reload` 模式下沿用） |
| `AUTOGLM_LOG_FILE` | `logs/autoglm_{time:YYYY-MM-DD}.log` | 日志文件路径 |
| `AUTOGLM_NO_LOG_FILE` | `0` | 置为 `1` 关闭文件日志 |

## 追踪与可观测性

详见[追踪与可观测性](../explanation/observability.md)。追踪默认开启，将 `AUTOGLM_TRACE_ENABLED` 设为 `0`/`false`/`no`/`off` 可关闭。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTOGLM_TRACE_ENABLED` | `1`（开启） | 是否启用执行追踪 |
| `AUTOGLM_TRACE_REPLAY_ENABLED` | `1`（开启） | 是否启用可回放追踪 |
| `AUTOGLM_TRACE_FILE` | `logs/trace_{date}.jsonl` | 追踪 JSONL 输出路径 |
| `AUTOGLM_TRACE_CAPTURE_SCREENSHOT` | `artifact` | 截图捕获模式 |
| `AUTOGLM_TRACE_CAPTURE_THINKING` | `1`（开启） | 置为 `0`/`false`/`no`/`off` 关闭追踪中的 thinking 内容 |
| `AUTOGLM_TRACE_CAPTURE_ACTION` | `1`（开启） | 置为 `0`/`false`/`no`/`off` 关闭追踪中的 action 内容 |

## 设备操作延迟（高级）

`PHONE_AGENT_*` 系列控制每个 ADB 操作后的等待时间（单位：秒），用于适配响应较慢的设备。多数默认 `1.0` 秒。常用项：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PHONE_AGENT_TAP_DELAY` | `1.0` | 点击后等待 |
| `PHONE_AGENT_SWIPE_DELAY` | `1.0` | 滑动后等待 |
| `PHONE_AGENT_TEXT_INPUT_DELAY` | `1.0` | 文本输入后等待 |
| `PHONE_AGENT_LAUNCH_DELAY` | `1.0` | 启动应用后等待 |
| `PHONE_AGENT_ADB_RESTART_DELAY` | `2.0` | 启用 TCP/IP 后等待 |

> 完整的 `PHONE_AGENT_*` 清单见源码 `AutoGLM_GUI/adb/timing.py`（含双击、长按、返回、Home、键盘切换等延迟项）。

## 示例（docker-compose）

```yaml
services:
  autoglm-gui:
    image: ghcr.io/suyiiyii/autoglm-gui:main
    environment:
      AUTOGLM_BASE_URL: https://open.bigmodel.cn/api/paas/v4
      AUTOGLM_MODEL_NAME: autoglm-phone
      AUTOGLM_API_KEY: sk-xxxxx
      AUTOGLM_ENABLE_WEB_TERMINAL: "1"
```
