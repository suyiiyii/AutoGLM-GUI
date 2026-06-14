# AutoGLM-GUI 测试指南

本目录包含 AutoGLM-GUI 项目的全部自动化测试。阅读本文档可以帮助你理解测试分类、运行方式以及覆盖率口径。

---

## 目录结构

```
tests/
├── *.py                              # 单元测试 / 契约测试 / 模块级集成测试
├── test_agent_integration.py         # Agent 集成测试（根目录）
├── e2e/
│   ├── conftest.py                   # E2E 共享 fixture（mock server、本地服务等）
│   ├── test_local_e2e.py             # 本地端到端测试
│   ├── test_docker_e2e.py            # Docker 端到端测试
│   ├── test_task_system_e2e.py       # 任务系统端到端测试
│   ├── test_trace_replay_e2e.py      # Trace 回放端到端测试
│   ├── test_runner.py                # 测试运行器相关测试
│   ├── device_agent/                 # Mock LLM / Mock Agent / 远程设备测试辅助
│   │   ├── mock_llm_server.py
│   │   ├── mock_agent_server.py
│   │   ├── mock_llm_client.py
│   │   ├── test_client.py
│   │   ├── test_remote_device.py
│   │   ├── test_e2e_with_adapter.py
│   │   └── ...
│   └── fixtures/
│       └── scenarios/                # Harness 场景数据
├── harness/                          # 测试 harness（当前预留）
└── mock_screenshots/                 # 测试用固定截图
```

---

## 测试分类

本项目将测试分为三个层级：

### 1. 单元测试（Unit Tests）

- **位置**：`tests/*.py` 中不依赖外部服务的测试
- **特点**：纯内存运行，使用 `monkeypatch`、`TestClient`、mock 对象
- **目标**：验证单个函数、类、模块的行为正确
- **示例**：`tests/test_health_api.py`、`tests/test_glm_async_agent.py`

### 2. 集成测试（Integration Tests）

- **位置**：`tests/*.py` 中标记 `@pytest.mark.integration` 的测试，以及 `tests/test_agent_integration.py`
- **特点**：需要启动多个模块或子进程，验证模块间协作
- **目标**：确保 API、Agent、设备管理层等模块组合后工作正常

### 3. 端到端测试（E2E Tests）

- **位置**：`tests/e2e/test_*_e2e.py` 和 `frontend/e2e/`
- **特点**：
  - 后端 E2E：启动完整 AutoGLM-GUI 服务，通过真实 HTTP 请求驱动
  - 前端 E2E：使用 Playwright 在真实浏览器中点击操作，对接真实前端 + 真实后端
- **依赖说明**：
  - **后端 E2E** 对接的是 **mock 设备**和 **mock 大模型 API**（见 `tests/e2e/device_agent/`）
  - **前端 E2E** 启动真实前后端，但后端同样对接 mock 设备和 mock LLM
- **判定标准**：
  > 这类测试属于 **带 mock 依赖的端到端测试（E2E with mocked external dependencies）**。它们从用户视角触发，覆盖完整的前后端链路，但外部系统（Android 设备、LLM 服务）被 mock 替代，以保证 CI 的可重复性和稳定性。

严格意义上的“全真实链路系统测试”需要连接真实 Android 设备和真实 LLM API，成本高、不稳定，通常只在本地验证或灰度阶段手动执行，不纳入 CI 门禁。

---

## 测试标记（Markers）

`pytest.ini` 中定义了以下标记：

| Marker | 含义 | 使用场景 |
|--------|------|----------|
| `unit` | 纯内存单元测试，无外部服务 | 单个函数、类、模块 |
| `contract` | API 行为契约，重构时不应破坏 | 稳定的 API 响应格式测试 |
| `integration` | 同进程跨模块集成测试 | 需要多个模块协作但不启动真实服务 |
| `e2e` | 端到端测试，启动真实服务或浏览器 | 后端 E2E / 前端 E2E |
| `release_gate` | 发布前必须通过的回归门控 | 核心流程的关键测试 |
| `anyio` | 异步测试（pytest-anyio 提供）| 测试 async/await 代码 |

运行指定标记的测试：

```bash
# 仅运行 release_gate
uv run pytest -m release_gate -v

# 仅运行集成测试
uv run pytest -m integration -v

# 排除 E2E / 集成，只跑轻量级测试
uv run pytest -m "not integration and not e2e" -v
```

---

## 如何运行测试

### 后端测试

```bash
# 安装开发依赖
uv sync --dev

# 运行全部 Python 测试
uv run pytest -v

# 运行特定文件
uv run pytest tests/test_health_api.py -v

# 运行本地 E2E（不需要 Docker）
uv run pytest tests/e2e/test_local_e2e.py -v

# 运行 Docker E2E
uv run pytest tests/e2e/test_docker_e2e.py -v -s
```

### 前端 E2E

```bash
cd frontend
pnpm install
pnpm exec playwright install chromium
pnpm test:e2e
```

前端 E2E 通过 `frontend/playwright.config.ts` 的 `webServer` 启动
`frontend/e2e/startE2EStack.mjs`，自动拉起：
- Vite 前端 dev server
- AutoGLM-GUI 后端服务
- mock LLM server
- mock agent server

前端 E2E 场景（`frontend/e2e/*.spec.ts`）：
- `scroll.spec.ts` — 流式响应期间聊天自动吸底（回归 #346）
- `trace-events.spec.ts` — 前端调试输出 + 后端 trace 事件持久化
- `device-state-routing.spec.ts` — 在 chat/history 间切换时保持选中设备（回归 #376）
- `abort-task.spec.ts` — 从 UI 中止正在运行的任务，验证 UI 恢复可输入、后端 task 状态为 `CANCELLED` 且事件含 `cancelled`
- `history-detail.spec.ts` — 任务完成后打开 History 详情对话框，校验任务文本、步骤、每步耗时与动作记录

### 前端 E2E 视频录制

Playwright 配置（`frontend/playwright.config.ts`）对每个用例录制视频，并生成 HTML 报告：

- `video: 'on'` — 每个用例都录制视频
- `trace: 'on'` — 每个用例都保留完整 trace（带真实时间轴，可逐步回放每个 action / 网络请求 / DOM 快照）
- `screenshot: 'only-on-failure'` — 失败用例保留截图
- `reporter: html` — 视频和 trace 内嵌进 HTML 报告

CI（`web-e2e.yml` / `coverage-e2e-frontend.yml`）会把 `playwright-report` 打包成 artifact 上传，运行结束后可在 Actions 运行页面下载。下载后解压，本地用浏览器打开 `playwright-report/index.html` 即可回放视频和 trace。

---

## 覆盖率口径

CI 中按测试模式分别生成并上传后端覆盖率：

| 模式 | CI Job | 命令 |
|------|--------|------|
| 单元 + 契约 | `unit-coverage` | `uv run pytest -m "not integration and not e2e" --cov=AutoGLM_GUI --cov-report=xml:coverage-unit.xml` |
| 集成测试 | `integration-coverage` | `uv run pytest -m integration --cov=AutoGLM_GUI --cov-report=xml:coverage-integration.xml` |
| 后端 E2E | `e2e-backend-coverage` | `COVERAGE_PROCESS_START=.coveragerc uv run pytest -m e2e --cov=AutoGLM_GUI --cov-report=xml:coverage-e2e-backend.xml` |
| 前端 E2E | `e2e-frontend-coverage` | `COVERAGE_E2E_FRONTEND=1 pnpm test:e2e`（backend 覆盖率数据由子进程生成） |

### 覆盖率说明

| 项目 | 说明 |
|------|------|
| **指标** | 行覆盖率（Line Coverage） |
| **工具** | pytest-cov（底层 coverage.py） |
| **统计范围** | 仅 `AutoGLM_GUI/` 目录下的 Python 生产代码 |
| **不计入** | `tests/`、`frontend/`、`electron/`、`scripts/`、`docs/` 等 |
| **测试组成** | 每种模式只统计该模式运行的测试所覆盖到的代码 |
| **Codecov flags** | `unit`、`integration`、`e2e-backend`、`e2e-frontend` |

### 子进程覆盖率

后端 E2E 和前端 E2E 中的 AutoGLM-GUI server 运行在子进程中。`.coveragerc` 配置为：

```ini
[run]
source = AutoGLM_GUI
parallel = True
concurrency = multiprocessing,thread
```

子进程入口通过 `coverage.process_startup()` 启动 coverage，退出时自动保存数据。

### 手动跑分模式覆盖率

```bash
# 单元 + 契约
uv run pytest -m "not integration and not e2e" --cov=AutoGLM_GUI --cov-report=term

# 集成
uv run pytest -m integration --cov=AutoGLM_GUI --cov-report=term

# 后端 E2E
COVERAGE_PROCESS_START=.coveragerc uv run pytest -m e2e --cov=AutoGLM_GUI --cov-report=term

# 前端 E2E（需要安装 Playwright 浏览器）
cd frontend
COVERAGE_E2E_FRONTEND=1 pnpm test:e2e
cd ..
uv run coverage combine
uv run coverage xml -o coverage-e2e-frontend.xml
```

---

## Mock 基础设施

为了在不依赖真实 Android 设备和真实 LLM 的情况下跑通 E2E，项目提供了一套 mock：

| 组件 | 文件 | 作用 |
|------|------|------|
| Mock LLM Server | `tests/e2e/device_agent/mock_llm_server.py` | 模拟 OpenAI 兼容 LLM API |
| Mock Agent Server | `tests/e2e/device_agent/mock_agent_server.py` | 模拟 Android 设备，接收 tap/swipe 等命令 |
| Mock LLM Client | `tests/e2e/device_agent/mock_llm_client.py` | 在测试中验证 LLM 调用次数和参数 |
| Mock Agent Client | `tests/e2e/device_agent/test_client.py` | 在测试中验证设备命令 |

这些 mock 由 `tests/e2e/conftest.py` 中的 fixture 启动，每个测试函数会获得独立的端口和进程。

---

## CI 中的测试

| Workflow | 触发条件 | 说明 |
|----------|----------|------|
| `integration-tests.yml` | PR/push 到 `main/dev` | 多 Python 版本跑 `pytest -v` |
| `codecov.yml` | PR/push 到 `main/dev` | 分模式跑后端覆盖率并上传 Codecov |
| `coverage-e2e-frontend.yml` | PR/push 到 `main/master` | 前端 E2E 同时收集 backend 覆盖率 |
| `release-gate.yml` | PR/push 到 `main/dev` | 跑 `pytest -m release_gate` |
| `web-e2e.yml` | PR 到 `main/master` | Windows runner 跑 Playwright E2E |
| `build.yml` | PR/push 到 `main` | Electron 多平台构建 |
| `pr-lint.yml` | PR | Ruff + ESLint + Prettier + TypeScript 类型检查 |

---

## 常见问题

**Q：为什么前端没有单元测试？**

A：目前前端只有 Playwright E2E，没有 Vitest/Jest 单元测试。组件、hooks、utils 的细粒度测试是后续提升方向。

**Q：E2E 测试里设备是假的，还算 E2E 吗？**

A：算。它是“带 mock 外部依赖的 E2E”，覆盖了真实前后端链路。真实设备 + 真实 LLM 属于更高成本的系统测试。

**Q：Coverage 85.50% 是单元测试跑出来的吗？**

A：不是。它是单元 + 集成 + E2E 全部跑完后统计的 `AutoGLM_GUI/` 行覆盖率。
