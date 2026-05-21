# GitHub Actions layout

The CI workflows are grouped by responsibility so that each layer runs once.

- `lint.yml`: style checks only. Backend Ruff lint/format and frontend ESLint/Prettier live here.
- `typecheck.yml`: static type checks only. Backend Pyright and frontend TypeScript live here.
- `tests.yml`: test layers only. It runs Python unit/contract tests, Python integration tests, frontend browser E2E, and Docker E2E.
- `build.yml`: buildability only. It builds the Python package with bundled frontend assets and verifies Electron artifacts on each supported platform.
- `_electron-build.yml`: reusable Electron build implementation used by CI and release workflows.
- `release.yml` and `docker-publish.yml`: publishing workflows. They should not add PR test coverage.
- `claude.yml` and `claude-auto-review.yml`: automation workflows, not CI test gates.

When adding a new check, place it at the lowest layer that proves the behavior:
lint/typecheck checks before tests, unit/contract tests before integration, integration before browser or Docker E2E, and build checks only for packaging concerns.
