# Trace 实施计划

## 背景

当前项目已经有常规日志和 Prometheus 指标，但缺少一条任务执行过程中的分段耗时追踪能力。结果是只能看到“这次执行很慢”，却无法快速判断是模型慢、截图慢、ADB 慢，还是代码里的固定等待导致的。

本计划的目标是为 AutoGLM-GUI 增加一套轻量 trace 系统，用于追踪单次执行中的关键步骤耗时，并为后续前端展示和聚合指标铺路。

## 总体设计

- 使用轻量级 span 模型，不引入新的 tracing 依赖。
- 每条任务用一个 `trace_id` 串起来。
- 每个关键步骤记录成一个 span，保留父子关系。
- 第一阶段只落本地 `jsonl` 文件，不修改前端协议。
- 后续阶段再把 trace 摘要暴露给 SSE、历史记录和 Prometheus。

## Trace 数据结构

每条 span 记录至少包含：

- `trace_id`
- `span_id`
- `parent_span_id`
- `name`
- `status`
- `start_time`
- `end_time`
- `duration_ms`
- `attrs`

输出文件：

- 默认写入 `logs/trace_YYYY-MM-DD.jsonl`
- 每行一条 JSON，便于 grep、jq、后续离线分析

## 第一阶段范围

第一阶段目标：完成“单次 trace 闭环”，让一次任务的关键耗时都能在本地 trace 文件中看到。

### 接入层级

1. API 层
   - `api.chat`
   - `api.chat.stream`
   - `api.layered_agent.chat`

2. Agent 执行层
   - `agent.stream`
   - `agent.step`
   - `step.capture_screenshot`
   - `step.get_current_app`
   - `step.llm`
   - `step.parse_action`
   - `step.execute_action`
   - `step.update_context`

3. Action 层
   - `action.execute`
   - `sleep.wait_action`
   - 输入法切换和文本输入相关 sleep

4. 设备与 IO 层
   - ADB 截图
   - ADB `dumpsys window`
   - ADB 点击、滑动、返回、Home、启动 App
   - ADB 输入法广播
   - Remote device 的 HTTP 请求

5. 固定等待
   - 所有热路径上的 `sleep` 单独记 span

### 第一阶段不做

- 不把 trace 明细直接推给前端
- 不改历史记录数据模型
- 不做 Prometheus trace 级别标签
- 不接入外部 tracing 后端

## 第二阶段计划

目标：让用户直接在运行结果里看到 step timing 摘要。

计划内容：

- 在 SSE `step` 事件里附带 `timings`
- 在历史记录中保存 step-level trace summary
- 增加“本次执行耗时拆解”视图

## 第三阶段计划

目标：增加跨任务聚合分析能力。

计划内容：

- 增加 Prometheus latency 指标
- 统计 LLM、截图、ADB 动作、sleep 的耗时分布
- 识别高频慢步骤和异常长尾

## 实施顺序

1. 新增 `AutoGLM_GUI/trace.py`
2. 先接 API 根 trace
3. 再接 `AsyncAgentBase` 主循环
4. 再接 GLM、Gemini、MAI 的 step 内部分段
5. 接入 `ActionHandler`
6. 接入 ADB 和 RemoteDevice 热路径 IO
7. 加最小测试和校验命令

## 验证方式

第一阶段完成后，至少要满足：

- 执行一次 `/api/chat` 或 `/api/chat/stream` 后会生成 trace 文件
- 同一个任务的 span 共享同一个 `trace_id`
- 可以在 trace 里看到 step、llm、screenshot、action、sleep 的耗时
- trace 写入失败不会影响主流程

## 预期收益

- 快速判断慢点到底在模型、截图、ADB 还是固定等待
- 为后续调优 `TIMING_CONFIG` 提供真实依据
- 为后续前端性能面板和 Prometheus 聚合打下统一基础
