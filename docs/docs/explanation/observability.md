---
title: 追踪与可观测性
sidebar_label: 追踪与可观测性
sidebar_position: 5
---

# 追踪与可观测性

AutoGLM-GUI 内置一套轻量的执行追踪（trace）系统，用来回答「这次任务到底慢在哪、错在哪」。本页解释它的设计与用法。

## 为什么需要追踪

一次任务执行跨越多个阶段：截图 → 应用检测 → 模型推理 → 解析 → 执行动作 → ADB 调用 → 等待。任何一步都可能慢或失败。如果只看最终「成功 / 失败」，根因无从查起。追踪把每一步记录成带时间、父子关系和属性的 span，让你能精确定位瓶颈。

## 默认开启

追踪默认启用。把 `AUTOGLM_TRACE_ENABLED` 设为 `0` / `false` / `no` / `off` 可关闭。span 以 JSONL 写入 `logs/trace_{date}.jsonl`，路径可用 `AUTOGLM_TRACE_FILE` 覆盖（见[环境变量](../reference/env-vars.md)）。

每次任务运行都会把自己的 `trace_id` 存入记录；`/api/tasks/*` 与 `/api/history/*` 的响应里都带这个值。要排查某次任务，先拿到它的 `trace_id`，再用它过滤 trace 文件即可。

## 追踪覆盖了什么

- **模型调用**：经典 Agent 发 `step.llm`；分层规划层的流式调用发 `model.call` 与 `layered.planner.*`。
- **工具调用**：分层规划层发 `tool.call` 和 `tool.result`；Gemini 的 Function Calling 发 `tool.call`。
- **设备 / ADB 调用**：设备封装与底层 ADB 操作发 `device.*` 与 `adb.*`。
- **记忆与持久化**：MAI 轨迹记忆发 `memory.read` / `memory.write`；分层会话发 `memory.*`；任务/历史写入发 `task_store.*` / `history.*`。
- **任务汇总**：任务结束追加一条 `trace_summary` 事件，并据同一份 trace 数据记录 Prometheus 时延指标。

## 怎么用来排障

1. 在后端正常运行下复现问题。
2. 在 `/api/tasks/{task_id}` 或 `/api/history/{serialno}/{record_id}` 找到这次任务，复制它的 `trace_id`。
3. 用该 `trace_id` 过滤 `logs/trace_{date}.jsonl`，查看各 span 的名称、父子关系、耗时和 `attrs`。
4. 历史详情里也有按阶段拆分的步骤耗时（截图、应用检测、LLM、解析、动作执行、ADB、sleep 等），可快速看出瓶颈。
5. 任务跑完后，`/api/metrics` 提供聚合的 Prometheus 直方图。

## 可回放追踪

`AUTOGLM_TRACE_REPLAY_ENABLED`（默认开启）会记录足以「回放」一次执行的数据（含截图等），便于事后复盘和复现，无需重新连接真机。

> 相关接口见 [REST API](../reference/rest-api.md) 的 `/api/metrics`、`/api/tasks/{task_id}/events`。
