# Contributing Guide

Thanks for helping improve AutoGLM-GUI. This document summarizes how to get the workspace ready, what commands to run, and how to submit high-quality contributions.

## Prerequisites

- **Python 3.11+** (project requires `>=3.11`)
- **Node 18+** and **pnpm** for frontend and docs work
- **uv** – the project uses it for dependency management and task scripts
- **ADB** in your `PATH` if you plan to run device-driven flows

## Setup

```bash
# Sync backend dependencies
uv sync

# Install frontend deps
cd frontend
pnpm install
```

Return to the repo root before running other scripts.

## Local development

- `uv run autoglm-gui --base-url http://localhost:8080/v1 --reload` starts the backend with auto-reload.
- `cd frontend && pnpm dev` starts the frontend dev server on `http://localhost:3000`.
- For docs changes run `cd docs && pnpm start` (or `pnpm build` to verify the static output).

## Verification before PR

- `uv run python scripts/lint.py` runs backend+frontend format/type checks.
- `uv run pytest -v` covers integration/test suites when your change touches core logic.
- Add screenshots or recordings for UI changes and mention them in the PR description.

## Workflow

1. Find an issue labeled `good first issue`, `help wanted`, `enhancement`, or `bug`.
2. Comment `/assign me` or leave a sentence indicating you will take it on. Wait for confirmation before starting.
3. Create a topic branch named `codex/<short-description>`.
4. Follow the code style and keep your diff focused on the changes that address the issue.

## Pull request expectations

- Title and commit messages should follow Conventional Commits (`feat:`, `fix:`, `docs:`, etc.).
- PR description should include:
  - Summary of what changed.
  - Related issue number (e.g., `Closes #123`).
  - Testing steps (commands run and outcomes).
- Tick off:
  - [ ] Commands from "Verification before PR" were run (if applicable).
  - [ ] Documentation updated (when behavior or setup changed).
  - [ ] Screenshots or recording attached for UI work.

## Communication and conduct

- Be respectful and patient in issues and PR comments.
- Provide context when asking for help; post logs or repro steps.
- Link to relevant docs instead of repeating the same instructions in each issue.

## Resources

- [Documentation site](https://auto-glm-gui-docs.vercel.app/docs) – the main user guide for installation, deployment, and features.
- [docs/internal/](./docs/internal/) – internal planning notes and architecture references for maintainers.
- [Issues](https://github.com/suyiiyii/AutoGLM-GUI/issues) – browse current work and claim tasks.

Thanks for contributing!
