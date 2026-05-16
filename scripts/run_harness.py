#!/usr/bin/env python3
"""Minimal local harness runner for stable integration scenarios.

Phase 1 scope:
- list runnable scenarios from tests/integration/fixtures/scenarios
- execute the meituan_message scenario through the existing local server +
  mock LLM + mock device + trace/replay path
- write a JSON report with artifact paths and a reproduction command

Non-goals:
- dynamic port architecture changes
- coverage / codecov policy
- custom structural checks
- full golden replay platform
- CI gate changes
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.integration.conftest import (  # noqa: E402
    _run_agent_server,
    _run_autoglm_server,
    _run_llm_server,
    find_free_port,
    wait_for_server,
)
from tests.integration.device_agent.mock_llm_client import (  # noqa: E402
    MockLLMTestClient,
)
from tests.integration.device_agent.test_client import (  # noqa: E402
    MockAgentTestClient,
)
from tests.integration.schema import TestScenarioSchema  # noqa: E402
from tests.integration.test_task_system_e2e import (  # noqa: E402
    _configure_mock_llm,
    _register_remote_device,
    _wait_for_task_completion,
)
from tests.integration.test_trace_replay_e2e import _read_jsonl  # noqa: E402


SCENARIOS_DIR = PROJECT_ROOT / "tests" / "integration" / "fixtures" / "scenarios"
DEFAULT_REPORT = PROJECT_ROOT / "test-results" / "harness" / "report.json"


@dataclass
class ServiceBundle:
    llm_url: str
    agent_url: str
    backend_url: str
    trace_file: Path
    trace_root: Path


def _timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def discover_scenarios() -> dict[str, Path]:
    scenarios: dict[str, Path] = {}
    for scenario_yaml in sorted(SCENARIOS_DIR.glob("*/scenario.yaml")):
        scenarios[scenario_yaml.parent.name] = scenario_yaml
    return scenarios


def _load_scenario_metadata(path: Path) -> dict[str, Any]:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    parsed = TestScenarioSchema.model_validate(raw)
    return {
        "name": path.parent.name,
        "test_name": parsed.test_name,
        "instruction": parsed.instruction,
        "max_steps": parsed.max_steps,
        "path": path,
    }


@contextmanager
def managed_process(
    target, args: tuple[Any, ...], ready_url: str, endpoint: str, timeout: float
) -> Iterator[None]:
    proc = multiprocessing.Process(target=target, args=args, daemon=True)
    proc.start()
    try:
        wait_for_server(ready_url, timeout=timeout, endpoint=endpoint)
        yield
    finally:
        proc.terminate()
        proc.join(timeout=3)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1)


@contextmanager
def running_services(run_dir: Path) -> Iterator[ServiceBundle]:
    llm_port = find_free_port(start=18000, end=18999)
    agent_port = find_free_port(start=19000, end=19999)
    backend_port = find_free_port(start=8000, end=8099)

    llm_url = f"http://127.0.0.1:{llm_port}"
    agent_url = f"http://127.0.0.1:{agent_port}"
    backend_url = f"http://127.0.0.1:{backend_port}"
    trace_file = run_dir / "trace.jsonl"

    with managed_process(
        _run_llm_server,
        (llm_port,),
        llm_url,
        "/test/stats",
        10.0,
    ):
        with managed_process(
            _run_agent_server,
            (agent_port, None),
            agent_url,
            "/test/commands",
            10.0,
        ):
            with managed_process(
                _run_autoglm_server,
                (backend_port, llm_url, str(trace_file)),
                backend_url,
                "/api/health",
                30.0,
            ):
                yield ServiceBundle(
                    llm_url=llm_url,
                    agent_url=agent_url,
                    backend_url=backend_url,
                    trace_file=trace_file,
                    trace_root=run_dir,
                )


def _collect_screenshot_paths(replay_file: Path) -> list[str]:
    if not replay_file.exists():
        return []

    screenshot_paths: list[str] = []
    for record in _read_jsonl(replay_file):
        if record.get("event_name") != "autoglm.step":
            continue
        step = record.get("step") or {}
        artifacts = step.get("artifacts") or {}
        screenshot_ref = artifacts.get("screenshot") or {}
        relative_path = screenshot_ref.get("path")
        if not relative_path:
            continue
        absolute_path = replay_file.parent / relative_path
        screenshot_paths.append(str(absolute_path))
    return screenshot_paths


def _save_task_events(
    backend_url: str, task_id: str, target: Path
) -> tuple[Path, list[dict[str, Any]]]:
    resp = httpx.get(f"{backend_url}/api/tasks/{task_id}/events", timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target, payload["events"]


def _build_reproduce_command(report_path: Path, scenario_name: str) -> str:
    return (
        "uv run python scripts/run_harness.py "
        f"--scenario {scenario_name} --report-json {report_path}"
    )


def run_meituan_harness(
    scenario_name: str,
    scenario_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_dir = report_path.parent / f"{scenario_name}-{_timestamp_slug()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata = _load_scenario_metadata(scenario_path)
    result: dict[str, Any] = {
        "scenario": scenario_name,
        "status": "failed",
        "failure_reason": None,
        "action_history": [],
        "task_id": None,
        "trace_id": None,
        "trace_file": None,
        "replay_file": None,
        "task_events_file": None,
        "screenshot_paths": [],
        "artifacts": {
            "scenario_path": str(scenario_path),
            "run_dir": str(run_dir),
            "trace_file": None,
            "replay_file": None,
            "task_events_file": None,
            "screenshots": [],
        },
        "reproduce_command": _build_reproduce_command(report_path, scenario_name),
        "instruction": metadata["instruction"],
        "test_name": metadata["test_name"],
        "task_status": None,
        "final_message": None,
        "llm_request_count": 0,
    }

    try:
        with running_services(run_dir) as services:
            result["artifacts"]["trace_file"] = str(services.trace_file)
            result["trace_file"] = str(services.trace_file)

            test_client = MockAgentTestClient(services.agent_url)
            llm_client = MockLLMTestClient(services.llm_url)
            try:
                llm_client.reset()
                test_client.reset()
                test_client.load_scenario(str(scenario_path))

                registered_device_id, registered_serial = _register_remote_device(
                    services.backend_url,
                    services.agent_url,
                )
                _configure_mock_llm(services.backend_url, services.llm_url)

                session_resp = httpx.post(
                    f"{services.backend_url}/api/task-sessions",
                    json={
                        "device_id": registered_device_id,
                        "device_serial": registered_serial,
                    },
                    timeout=10,
                )
                session_resp.raise_for_status()
                session_id = session_resp.json()["id"]

                submit_resp = httpx.post(
                    f"{services.backend_url}/api/task-sessions/{session_id}/tasks",
                    json={"message": metadata["instruction"]},
                    timeout=10,
                )
                submit_resp.raise_for_status()
                queued_task = submit_resp.json()
                task_id = str(queued_task["id"])
                result["task_id"] = task_id

                final_task = _wait_for_task_completion(
                    services.backend_url, task_id, timeout=30.0
                )
                result["task_status"] = final_task["status"]
                result["trace_id"] = (
                    str(final_task["trace_id"]) if final_task.get("trace_id") else None
                )
                result["final_message"] = final_task.get("final_message")

                commands = test_client.get_commands()
                result["action_history"] = commands
                result["llm_request_count"] = llm_client.get_stats()["request_count"]

                events_path, events = _save_task_events(
                    services.backend_url,
                    task_id,
                    run_dir / "task-events.json",
                )
                result["artifacts"]["task_events_file"] = str(events_path)
                result["task_events_file"] = str(events_path)

                replay_file = None
                if result["trace_id"]:
                    replay_file = (
                        services.trace_root
                        / "runs"
                        / result["trace_id"]
                        / "replay.jsonl"
                    )
                    result["artifacts"]["replay_file"] = str(replay_file)
                    result["replay_file"] = str(replay_file)
                    screenshot_paths = _collect_screenshot_paths(replay_file)
                    result["artifacts"]["screenshots"] = screenshot_paths
                    result["screenshot_paths"] = screenshot_paths

                if final_task["status"] == "SUCCEEDED":
                    result["status"] = "passed"
                    result["failure_reason"] = None
                else:
                    result["status"] = "failed"
                    result["failure_reason"] = (
                        f"Task finished with status {final_task['status']}"
                    )

                if result["failure_reason"] is None:
                    done_event = next(
                        (
                            event
                            for event in events
                            if event.get("event_type") == "done"
                        ),
                        None,
                    )
                    if done_event:
                        payload = done_event.get("payload") or {}
                        maybe_error = payload.get("error")
                        if maybe_error:
                            result["failure_reason"] = maybe_error
                            result["status"] = "failed"
            finally:
                test_client.close()
                llm_client.close()
    except Exception as exc:
        result["status"] = "failed"
        result["failure_reason"] = str(exc)

    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def print_summary(result: dict[str, Any], report_path: Path) -> None:
    print("=" * 72)
    print("Harness Result")
    print("=" * 72)
    print(f"scenario:        {result['scenario']}")
    print(f"status:          {result['status']}")
    print(f"task_status:     {result.get('task_status')}")
    print(f"task_id:         {result.get('task_id')}")
    print(f"trace_id:        {result.get('trace_id')}")
    print(f"final_message:   {result.get('final_message')}")
    print(f"failure_reason:  {result.get('failure_reason')}")
    print(f"report_json:     {report_path}")
    print(f"trace_file:      {result['artifacts'].get('trace_file')}")
    print(f"replay_file:     {result['artifacts'].get('replay_file')}")
    print(f"task_events:     {result['artifacts'].get('task_events_file')}")
    print(f"screenshots:     {len(result['artifacts'].get('screenshots', []))}")
    print(f"reproduce:       {result['reproduce_command']}")
    print("action_history:")
    for index, action in enumerate(result.get("action_history", []), start=1):
        print(f"  {index}. {json.dumps(action, ensure_ascii=False)}")
    print("=" * 72)


def cmd_list() -> int:
    for scenario_name, scenario_path in discover_scenarios().items():
        metadata = _load_scenario_metadata(scenario_path)
        print(
            f"{scenario_name}\t{metadata['test_name']}\t{scenario_path.relative_to(PROJECT_ROOT)}"
        )
    return 0


def cmd_run(scenario_name: str, report_path: Path) -> int:
    scenarios = discover_scenarios()
    scenario_path = scenarios.get(scenario_name)
    if scenario_path is None:
        print(f"Unknown scenario: {scenario_name}", file=sys.stderr)
        return 2

    if scenario_name != "meituan_message":
        print(
            f"Scenario {scenario_name} is not enabled in Phase 1. "
            "Only meituan_message is supported in the first cut.",
            file=sys.stderr,
        )
        return 2

    result = run_meituan_harness(scenario_name, scenario_path, report_path)
    print_summary(result, report_path)
    return 0 if result["status"] == "passed" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal local harness runner")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List runnable scenarios discovered under tests/integration/fixtures/scenarios",
    )
    parser.add_argument(
        "--scenario",
        help="Scenario name to execute (Phase 1 supports meituan_message only)",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write the JSON report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.list:
        return cmd_list()

    if args.scenario:
        return cmd_run(args.scenario, args.report_json.resolve())

    print("Either --list or --scenario must be provided.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
