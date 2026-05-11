# AGENTS.md

## Project context
- AutoGLM-GUI is an AI-driven Android automation project with a Python backend and separate frontend/electron apps.
- Backend code lives in `AutoGLM_GUI/` (API entrypoint examples: `AutoGLM_GUI/api/__init__.py`, CLI entry: `AutoGLM_GUI/__main__.py`).
- Web frontend lives in `frontend/` (entry: `frontend/src/main.tsx`), desktop packaging lives in `electron/`.
- Build/lint orchestration scripts are in `scripts/` (`scripts/lint.py`, `scripts/build.py`, `scripts/build_electron.py`).
- Tests are in `tests/` and `tests/integration/` (example: `tests/test_metrics.py`, `tests/integration/test_agent_integration.py`).

## Setup
- Required Python: `>=3.11` (from `pyproject.toml`).
- Required Node/pnpm: Node.js `18+` and `pnpm` (from `CONTRIBUTING.md`); CI commonly runs Node `24` (from `.github/workflows/pr-lint.yml`).
- Required tools: `uv` (dependency sync and task runner), `adb` in PATH (from `CONTRIBUTING.md`).
- Install backend dependencies (repo root): `uv sync`
- Install frontend dependencies: `cd frontend && pnpm install`
- Optional Electron dependencies (when working on desktop app): `cd electron && pnpm install`
- Start backend dev server: `uv run autoglm-gui --base-url http://localhost:8080/v1 --reload`
- Start frontend dev server: `cd frontend && pnpm dev`

## Commands
### Lint
- Quick (backend only, check mode): `uv run python scripts/lint.py --backend --check-only`
- Quick (frontend only, check mode): `uv run python scripts/lint.py --frontend --check-only`
- Full (check mode): `uv run python scripts/lint.py --check-only`

### Format
- Full auto-fix (backend + frontend): `uv run python scripts/lint.py`
- Backend format check: `uv run ruff format --check --diff`
- Backend format apply: `uv run ruff format`
- Frontend format check: `cd frontend && pnpm format:check`
- Frontend format apply: `cd frontend && pnpm format`

### Typecheck
- Backend typecheck: `uv run pyright AutoGLM_GUI/`
- Frontend typecheck: `cd frontend && pnpm type-check`

### Unit tests
- TODO: 未找到“仅单元测试”的专用命令（已检查 `README.md`、`CONTRIBUTING.md`、`pyproject.toml`、`tests/`、`.github/workflows/integration-tests.yml`）。

### Integration or e2e
- Integration tests (CI uses this): `uv run pytest -v`
- Docker e2e (specific file): `uv run pytest tests/integration/test_docker_e2e.py -v -s`

### Build
- Build frontend + copy to backend static: `uv run python scripts/build.py`
- Build package (includes wheel build): `uv run python scripts/build.py --pack`
- Frontend-only build path: `cd frontend && pnpm build`
- Electron app build (CI mode): `uv run python scripts/build_electron.py --publish never`
- Docker compose runtime (deploy-style): `docker-compose up -d`

## Debugging and observability
### Trace files
- Backend tracing is enabled by default unless `AUTOGLM_TRACE_ENABLED` is set to `0`, `false`, `no`, or `off`.
- Trace spans are written as JSONL to `logs/trace_{date}.jsonl` by default. Override the path with `AUTOGLM_TRACE_FILE`, for example: `AUTOGLM_TRACE_FILE=/tmp/autoglm_trace_{date}.jsonl`.
- Each task run stores its `trace_id` in `task_runs.trace_id`. The same value is returned by `/api/tasks/*` and `/api/history/*`.
- To inspect one task, get its `trace_id` from the task or history response, then filter the JSONL trace file by that value.

### Trace coverage
- Model calls: classic agents emit `step.llm`; layered planner streaming emits `model.call` and `layered.planner.*`.
- Tool calls: layered planner emits `tool.call` and `tool.result`; Gemini function calling emits `tool.call`.
- ADB/device calls: device wrappers and low-level ADB operations emit `device.*` and `adb.*` spans.
- Memory and persistence: MAI trajectory memory emits `memory.read` and `memory.write`; layered planner SQLite sessions emit `memory.read`, `memory.write`, `memory.delete`, and `memory.clear`; task/history writes emit `task_store.*` and `history.*`.
- Task summaries: task completion appends a `trace_summary` event and records Prometheus latency metrics from the same trace data.

### Debugging workflow
- Reproduce the issue with the backend running normally.
- Find the task in `/api/tasks/{task_id}` or `/api/history/{serialno}/{record_id}` and copy `trace_id`.
- Filter `logs/trace_{date}.jsonl` for that `trace_id`; inspect span names, parent span ids, durations, and `attrs`.
- Use step timing chips in history for a quick breakdown of screenshot, app detection, LLM, parsing, action execution, ADB, sleep, and other time.
- Use `/api/metrics` for aggregate Prometheus histograms after tasks complete.

## Do / Don’t
### Do
- Prefer minimal, localized changes; follow existing patterns in nearby files.
- Reuse existing scripts in `scripts/` instead of introducing parallel tooling.
- Keep backend/frontend boundaries clear (`AutoGLM_GUI/` vs `frontend/`).
- Add or update tests near changed logic when feasible (examples in `tests/` and `tests/integration/`).

### Don’t
- Don’t perform broad refactors unrelated to the task.
- Don’t introduce new dependencies/toolchains if existing `uv`/`pnpm` scripts already solve the problem.
- Don’t change public API/CLI behavior (e.g., `autoglm-gui` options) unless explicitly requested.
- Don’t edit CI workflow semantics unless the task is CI-related.

## Safe change workflow
1. Understand scope first: read relevant module + one existing similar implementation.
2. Make the smallest viable change in-place.
3. Run minimal verification before full verification.
4. Summarize what changed, what was run, and remaining risk.

Recommended minimal verification set:
- Python-only changes: `uv run python scripts/lint.py --backend --check-only`
- Frontend-only changes: `uv run python scripts/lint.py --frontend --check-only`
- Cross-cutting or risky changes: `uv run python scripts/lint.py --check-only` + `uv run pytest -v`

## When unsure
- Ask first: target scope, compatibility constraints, and whether behavior/API changes are allowed.
- Propose a short plan before coding:
- Step 1: confirm files to touch.
- Step 2: implement minimal patch.
- Step 3: run agreed verification commands.
- Step 4: report diff + validation results + follow-up options.
