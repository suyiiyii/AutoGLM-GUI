# AutoGLM-GUI 测试指南

本目录包含 AutoGLM-GUI 项目的全部自动化测试。阅读本文档可以帮助你理解测试分类、运行方式以及覆盖率口径。

---

## 目录结构

```
tests/
├── *.py                              # 单元测试 / 契约测试 / 模块级集成测试
├── integration/
│   ├── conftest.py                   # 集成测试共享 fixture（mock server、本地服务等）
│   ├── test_local_e2e.py             # 本地端到端测试
│   ├── test_docker_e2e.py            # Docker 端到端测试
│   ├── test_task_system_e2e.py       # 任务系统端到端测试
│   ├── test_trace_replay_e2e.py      # Trace 回放端到端测试
│   ├── test_agent_integration.py     # Agent 集成测试
│   ├── test_runner.py                # 测试运行器相关测试
│   └── device_agent/                 # Mock LLM / Mock Agent / 远程设备测试辅助
│       ├── mock_llm_server.py
│       ├── mock_agent_server.py
│       ├── mock_llm_client.py
│       ├── test_client.py
│       ├── test_remote_device.py
│       ├── test_e2e_with_adapter.py
│       └── ...
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
| `contract` | API 行为契约，重构时不应破坏 | 稳定的 API 响应格式测试 |
| `integration` | 跨模块或多进程集成测试 | 需要子进程 / mock server |
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

前端 E2E 的 `globalSetup` 会自动启动：
- Vite 前端 dev server
- AutoGLM-GUI 后端服务
- mock LLM server
- mock agent server

---

## 覆盖率口径

CI 中通过 `.github/workflows/codecov.yml` 生成并上传覆盖率：

```bash
uv run pytest -v --cov=AutoGLM_GUI --cov-report=xml:coverage.xml --cov-report=term-missing:skip-covered
```

### 覆盖率说明

| 项目 | 说明 |
|------|------|
| **指标** | 行覆盖率（Line Coverage） |
| **工具** | pytest-cov（底层 coverage.py） |
| **统计范围** | 仅 `AutoGLM_GUI/` 目录下的 Python 生产代码 |
| **不计入** | `tests/`、`frontend/`、`electron/`、`scripts/`、`docs/` 等 |
| **测试组成** | 由单元测试 + 集成测试 + E2E 测试共同贡献，不是单一测试类型的覆盖率 |
| **当前数值** | 约 **85.50%**（以 Codecov 最新报告为准） |

### 重要提示

- Codecov 的 85.50% 是**全量 Python 测试**一起跑出来的混合覆盖率。
- 它不是纯单元测试覆盖率，也不是纯 E2E 覆盖率。
- 默认是**行覆盖**，不是分支覆盖（Branch Coverage）。
- 本项目没有额外配置 `.coveragerc` 或 `[tool.coverage]`，使用 pytest-cov 默认行为。

如果你想看不同层级的覆盖率，可以手动拆分：

```bash
# 单元 + 契约测试贡献的覆盖率
uv run pytest -m "not integration and not e2e" --cov=AutoGLM_GUI --cov-report=term

# 集成 + E2E 贡献的覆盖率
uv run pytest -m "integration or e2e" --cov=AutoGLM_GUI --cov-report=term
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
| `codecov.yml` | PR/push 到 `main/dev` | 跑覆盖率并上传 Codecov |
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
