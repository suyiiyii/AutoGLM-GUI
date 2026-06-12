#!/usr/bin/env python3
"""Run backend coverage for integration and E2E test modes."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


@dataclass(frozen=True)
class CoverageMode:
    name: str
    coverage_file: str
    xml_file: str
    command: list[str]
    cwd: Path
    uses_coverage_run: bool = True


MODES = {
    "integration": CoverageMode(
        name="integration",
        coverage_file=".coverage.integration",
        xml_file="coverage.integration.xml",
        command=[
            "uv",
            "run",
            "coverage",
            "run",
            "-m",
            "pytest",
            "tests/integration",
            "tests/test_trace_observability_integration.py",
            "-v",
        ],
        cwd=PROJECT_ROOT,
    ),
    "backend-e2e": CoverageMode(
        name="backend-e2e",
        coverage_file=".coverage.backend-e2e",
        xml_file="coverage.backend-e2e.xml",
        command=[
            "uv",
            "run",
            "coverage",
            "run",
            "-m",
            "pytest",
            "tests/e2e/backend",
            "--ignore=tests/e2e/backend/test_docker.py",
            "-v",
            "-s",
        ],
        cwd=PROJECT_ROOT,
    ),
    "frontend-e2e": CoverageMode(
        name="frontend-e2e",
        coverage_file=".coverage.frontend-e2e",
        xml_file="coverage.frontend-e2e-backend.xml",
        command=["pnpm", "test:e2e"],
        cwd=FRONTEND_DIR,
        uses_coverage_run=False,
    ),
}


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        check=True,
        shell=platform.system() == "Windows" and cmd[0] in {"pnpm", "npm", "yarn"},
    )


def _remove_coverage_data(coverage_file: Path) -> None:
    for path in coverage_file.parent.glob(f"{coverage_file.name}*"):
        if path.is_file():
            path.unlink()


def _coverage_env(mode: CoverageMode) -> dict[str, str]:
    env = os.environ.copy()
    env["COVERAGE_FILE"] = str(PROJECT_ROOT / mode.coverage_file)
    if not mode.uses_coverage_run:
        env["COVERAGE_PROCESS_START"] = str(PROJECT_ROOT / "pyproject.toml")
    return env


def _run_mode(mode: CoverageMode, *, keep_data: bool, report: bool) -> None:
    coverage_file = PROJECT_ROOT / mode.coverage_file
    xml_file = PROJECT_ROOT / mode.xml_file
    env = _coverage_env(mode)

    if not keep_data:
        _remove_coverage_data(coverage_file)
        if xml_file.exists():
            xml_file.unlink()

    _run(mode.command, cwd=mode.cwd, env=env)
    _run(["uv", "run", "coverage", "combine"], cwd=PROJECT_ROOT, env=env)

    if report:
        _run(["uv", "run", "coverage", "report"], cwd=PROJECT_ROOT, env=env)

    _run(
        ["uv", "run", "coverage", "xml", "-o", str(xml_file)],
        cwd=PROJECT_ROOT,
        env=env,
    )
    print(f"\nWrote {xml_file.relative_to(PROJECT_ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backend coverage for one test mode."
    )
    parser.add_argument(
        "mode",
        choices=[*MODES.keys(), "all"],
        help="Coverage mode to run.",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep existing .coverage files before running.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip the terminal coverage report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modes = MODES.values() if args.mode == "all" else [MODES[args.mode]]
    for mode in modes:
        print(f"\n=== {mode.name} backend coverage ===")
        _run_mode(mode, keep_data=args.keep_data, report=not args.no_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
