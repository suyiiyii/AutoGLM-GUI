---
title: CLI 命令行参数
sidebar_label: CLI 参数
sidebar_position: 1
---

# CLI 命令行参数

`autoglm-gui` 命令支持以下参数。所有参数均可选；模型相关参数也可在 Web 界面或[环境变量](./env-vars.md)中配置。

```bash
autoglm-gui [选项]
```

## 模型服务

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--base-url` | 无 | 模型 API 的基础地址，例如 `http://localhost:8080/v1` |
| `--model` | `autoglm-phone-9b` | 使用的模型名称；不指定时取该默认值或配置文件中的值 |
| `--apikey` | 无 | 模型 API 密钥；不指定时取环境变量 `AUTOGLM_API_KEY` |

## 服务器

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 服务器绑定的主机地址。部署到服务器供外部访问时设为 `0.0.0.0` |
| `--port` | 自动（从 8000 起找空闲端口） | 服务器监听端口 |
| `--no-browser` | 关闭 | 启动时不自动打开浏览器 |
| `--reload` | 关闭 | 开发模式：代码变更自动重载 |
| `--ssl-keyfile` | 无 | HTTPS 私钥文件路径 |
| `--ssl-certfile` | 无 | HTTPS 证书文件路径 |

> 实时画面预览（基于 WebCodecs）在非 `localhost` 访问时需要 HTTPS。对外部署时建议配置 `--ssl-keyfile` 与 `--ssl-certfile`，或在反向代理层启用 TLS。

## 日志

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--log-level` | `INFO` | 控制台日志级别，可选 `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `--log-file` | `logs/autoglm_{time:YYYY-MM-DD}.log` | 日志文件路径，支持 `{time}` 占位 |
| `--no-log-file` | 关闭 | 不写日志文件，仅输出到控制台 |

## 高级

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--layered-max-turns` | `50` | [分层代理模式](../explanation/layered-agent.md)的最大轮数，最小值 1 |
| `--adb-terminal-repl` | 关闭 | 启动 ADB 终端 REPL（内部/调试用，通常无需使用） |

## 示例

```bash
# 智谱 BigModel
autoglm-gui \
  --base-url https://open.bigmodel.cn/api/paas/v4 \
  --model autoglm-phone \
  --apikey sk-xxxxx

# 部署到服务器对外提供（监听所有网卡、不开浏览器）
autoglm-gui --host 0.0.0.0 --port 8000 --no-browser

# 指向自建的 vLLM / SGLang 服务
autoglm-gui --base-url http://localhost:8080/v1 --model autoglm-phone-9b
```

> 与命令行参数对应的环境变量见[环境变量](./env-vars.md)。
