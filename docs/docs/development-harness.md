---
id: development-harness
title: Harness Engineering 路线图
---

# Harness Engineering 路线图

本文是 issue [#387](https://github.com/suyiiyii/AutoGLM-GUI/issues/387) 的 Phase 0 交付，用于把 Harness Engineering 从一个“大实现议题”校准成可逐步合并的工程路线图。

## 执行规则

- 每个阶段必须单独提交 PR。
- 每个 PR 完成后只进入 review，不自动进入下一阶段。
- 只有项目负责人合并当前阶段 PR 后，团队才启动下一阶段。
- 每个阶段都必须有明确验收方式，不能只提交“铺路但不可验证”的改动。

## 当前基线

本轮盘点基于 `origin/main@6155f55e8effec7e6c87b749ffbf4f6d156c9e72`。后续阶段开始前，也应在对应任务里写明当时的 main commit，避免不同 worktree 看到不同现状。

### 已有能力

| 领域 | 当前基础 |
| --- | --- |
| 后端测试 | `tests/` 和 `tests/integration/` 已有 pytest 覆盖 |
| 测试分层 | `pytest.ini` 定义了 `contract`、`integration`、`release_gate` markers |
| Release gate | `.github/workflows/release-gate.yml` 运行后端 lint 和 `pytest -m "release_gate"` |
| Coverage | `.github/workflows/codecov.yml` 上传后端 coverage |
| 前端 E2E | `frontend/e2e/trace-events.spec.ts` 已能通过真实 UI + mock 服务验证 trace 事件 |
| E2E 服务启动 | `scripts/start_e2e_services.py` 启动 mock LLM、mock agent 和 backend |
| Trace / replay | `tests/test_trace.py` 和 `tests/integration/test_trace_replay_e2e.py` 覆盖 trace / replay 文件 |
| Agent 调试说明 | `AGENTS.md` 已记录 trace 文件、trace_id 和调试流程 |
| Scenario fixtures | `tests/integration/fixtures/scenarios/` 下已有 `meituan_message`、`wechat_multi_step` 等场景 |

### 当前缺口

- 缺少一个 agent 友好的统一 harness 入口。
- 现有 scenario、trace、mock device、mock LLM 能力分散在测试和脚本中，没有形成单命令反馈闭环。
- E2E 服务仍依赖固定端口，例如 `8000`、`18000`、`18003`，不适合多 worktree / 多 agent 并发。
- Golden replay 还没有稳定的 normalized comparison 机制。
- CI 现在有基础 gate，但没有专门的 harness report / artifact 上传流程。
- 项目特定结构规则还没有被机械化检查。
- Coverage 当前更适合作为观测指标，不适合在 harness 首版直接变成 blocking gate。

## 总体原则

Harness Engineering 的目标不是一次性造完整平台，而是让 coding agent 和 reviewer 更快得到确定、可复现、可解释的反馈。

因此，本路线图按“先可用，再稳定，再进 CI，再治理”的顺序推进。

## 阶段拆分

### Phase 0：路线图与现状盘点

目标：

- 明确当前基础设施现状。
- 把 #387 从单个实现任务校准成 umbrella / roadmap。
- 锁定后续阶段的边界和非目标范围。

验收：

- 本文档合入。
- 没有业务代码改动。
- 没有 CI gate 行为改动。

### Phase 1：最小 Harness Runner

目标：

- 新增一个统一入口，例如：

```bash
uv run python scripts/run_harness.py --list
uv run python scripts/run_harness.py --scenario meituan_message --report-json test-results/harness/report.json
```

- 复用现有 mock LLM、mock device、scenario fixture、trace / replay 基础。
- 首批只接入 1 到 2 个稳定 mock scenario，例如 `meituan_message` 和 `wechat_multi_step`。
- 输出 console summary 和 JSON report。

JSON report 至少包含：

- `scenario`
- `status`
- `failure_reason`
- `action_history`
- `task_id`
- `trace_id`
- trace / replay / screenshot artifact 路径
- reproduce command

非目标：

- 不做动态端口改造。
- 不做 coverage gate。
- 不做 custom structural checks。
- 不做完整 golden replay 平台。
- 不做大规模 scenario matrix。

### Phase 2：Normalized Golden Replay

目标：

- 对少数稳定场景引入 normalized golden comparison。
- 只比较语义稳定字段，例如 action sequence、required spans、replay event completeness、final status。
- 忽略 timestamps、durations、UUID、trace_id、临时路径、base64 截图等非确定字段。
- 失败时输出 compact diff，指出缺失 span、错误 action、事件顺序问题或缺失 artifact。

非目标：

- 不对所有 scenario 建 golden。
- 不提交运行截图、trace 大文件等高体积产物。

### Phase 3：Harness Artifacts in CI

目标：

- 在 CI 中保留 harness 失败产物。
- 上传 JSON report、trace、replay、必要截图等 artifact。
- 先作为非阻塞或小范围 gate 观察稳定性，再决定是否进入主 release gate。

非目标：

- 不立即替代现有 release gate。
- 不立即扩大到所有 agent 类型。

### Phase 4：Parallel-Safe E2E Ports

目标：

- 将 E2E 服务从固定端口逐步改成动态端口。
- 明确处理 backend URL、Vite proxy、Playwright base URL、URL JSON、PID cleanup。
- 确保多 worktree / 多 agent 并发运行时不会互相抢端口。

注意：

- 该阶段会影响 E2E 启动链路，必须单独 PR、单独验证。
- 不要和 Phase 1 runner 混在同一 PR 中。

### Phase 5：Project-Specific Structural Checks

目标：

- 只把低误报、项目特定、反复踩坑的规则机械化。
- 优先候选：
  - scenario 文件必须通过 schema 校验；
  - 新增 E2E 测试不允许硬编码固定端口，除非显式豁免；
  - 新增 harness 命令需要同步更新 agent-facing 文档。

非目标：

- 不做泛化 style policing。
- 不一次性加入大量规则。

### Phase 6：Coverage / Codecov Policy

目标：

- 在 harness 稳定后，再讨论 patch coverage 或关键模块 coverage 是否 blocking。
- 先从信息性报告和趋势观察开始。

非目标：

- 不在 Harness MVP 首版设置全局 coverage 阈值。
- 不因为覆盖率数字牺牲 agent feedback loop 的落地速度。

## 推荐 PR 队列

| PR | 内容 | 可合并标准 |
| --- | --- | --- |
| PR 1 | Phase 0 文档与路线图 | 文档清楚，无业务/CI 行为改动 |
| PR 2 | Phase 1 最小 runner | `--list` 和单 scenario JSON report 可运行 |
| PR 3 | 第二个 scenario + report 稳定化 | 证明 runner 不是单场景 demo |
| PR 4 | Phase 2 golden replay 试点 | normalized diff 稳定、不比脆弱字段 |
| PR 5 | Phase 3 CI artifact 上传 | 失败可下载 report/trace/replay |
| PR 6 | Phase 4 dynamic ports | 不破坏现有 Playwright/Vite/backend 启动 |
| PR 7 | Phase 5 structural checks | 只加入低误报规则 |
| PR 8 | Phase 6 coverage policy | 基于真实稳定性决定是否 blocking |

## 第一阶段完成后的下一步

本文档合入后，下一阶段只应启动 Phase 1：最小 Harness Runner。启动前需要创建单独任务，并明确本阶段不包含 dynamic ports、coverage gate、custom checks 和完整 golden replay 平台。
