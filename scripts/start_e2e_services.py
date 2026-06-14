#!/usr/bin/env python3
"""Start all backend services for E2E testing.

Launches three services and writes their URLs to a JSON file so Playwright
tests can discover them.  Waits for SIGTERM/SIGINT, then tears everything down.

Usage:
    python scripts/start_e2e_services.py [--output urls.json]
"""

import argparse
import json
import multiprocessing
import os
import random
import signal
import socket
import sys
import time
from contextlib import closing
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _port_is_free(port):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _find_free_port(start_port, end_port):
    # Randomize the scan start so concurrent worktrees / agents are less likely
    # to race for the same low ports.  Sequential scan from the beginning would
    # make every instance try 18000, 19000, and 8000 first.
    range_size = end_port - start_port + 1
    offset = random.randint(0, range_size - 1)
    for i in range(range_size):
        port = start_port + (offset + i) % range_size
        if _port_is_free(port):
            return port
    raise RuntimeError(f"No free port found in range {start_port}-{end_port}")


def wait_for_server(url, timeout=30.0, endpoint="/test/stats"):
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(f"{url}{endpoint}", timeout=1.0)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Server at {url} failed to start within {timeout}s")


def _terminate_processes(processes):
    for proc in reversed(processes):
        if not proc.is_alive():
            continue
        # Use SIGINT so uvicorn subprocesses run atexit handlers, which is
        # needed for coverage data to be flushed.
        try:
            os.kill(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        proc.join(timeout=15)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)


def _write_pid_file(pid_output, processes):
    if not pid_output:
        return
    pids = [proc.pid for proc in processes if proc.pid]
    with open(pid_output, "w") as f:
        json.dump({"launcher_pid": os.getpid(), "service_pids": pids}, f)


def _run_llm_server(port):
    from tests.e2e.device_agent.mock_llm_server import run_server

    run_server(port=port, log_level="warning")


def _run_agent_server(port, scenario_path=None):
    import uvicorn
    from tests.e2e.device_agent.mock_agent_server import create_app

    app = create_app(scenario_path=scenario_path)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _run_autoglm_server(port, llm_url):
    import os

    # Start coverage in subprocess when COVERAGE_PROCESS_START is set.
    if os.environ.get("COVERAGE_PROCESS_START"):
        import coverage

        coverage.process_startup()

    import uvicorn

    os.environ["AUTOGLM_BASE_URL"] = llm_url + "/v1"
    os.environ["AUTOGLM_MODEL_NAME"] = "mock-glm-model"
    os.environ["AUTOGLM_API_KEY"] = "mock-key"
    os.environ["HOME"] = "/tmp"
    from AutoGLM_GUI.server import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description="Start E2E test services")
    parser.add_argument(
        "--output", default=None, help="JSON output file for service URLs"
    )
    parser.add_argument(
        "--pid-output", default=None, help="JSON output file for service PIDs"
    )
    parser.add_argument("--scenario", default=None, help="Scenario YAML for mock agent")
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Enable Python coverage for the AutoGLM-GUI backend process",
    )
    parser.add_argument(
        "--dynamic-ports",
        action="store_true",
        help="Choose free ports automatically for backend and mock services",
    )
    args = parser.parse_args()

    if args.coverage:
        os.environ["COVERAGE_PROCESS_START"] = ".coveragerc"

    if args.dynamic_ports:
        # Allocate free ports so multiple worktrees / agents can run E2E in
        # parallel. These ranges intentionally do not overlap with the backend
        # E2E fixture ranges in tests/e2e/conftest.py.
        llm_port = _find_free_port(21000, 21999)
        agent_port = _find_free_port(22000, 22999)
        backend_port = _find_free_port(8100, 8199)
    else:
        # Use fixed ports so vite proxy (localhost:8000) works correctly.
        # If a port is in use the test will fail — free it up and retry.
        llm_port = 18003
        agent_port = 18000
        backend_port = 8000
        for port, name in [
            (llm_port, "mock LLM"),
            (agent_port, "mock agent"),
            (backend_port, "backend"),
        ]:
            if not _port_is_free(port):
                print(f"[E2E Services] ERROR: Port {port} ({name}) is already in use!")
                print("[E2E Services] Please free the port and retry.")
                sys.exit(1)

    llm_url = f"http://127.0.0.1:{llm_port}"
    agent_url = f"http://127.0.0.1:{agent_port}"
    backend_url = f"http://127.0.0.1:{backend_port}"
    output_path = args.output or os.path.join(
        PROJECT_ROOT, "frontend", "e2e", ".service_urls.json"
    )

    print(f"[E2E Services] LLM server:     {llm_url}")
    print(f"[E2E Services] Agent server:   {agent_url}")
    print(f"[E2E Services] Backend server: {backend_url}")

    started_processes = []
    try:
        # Start mock LLM
        llm_proc = multiprocessing.Process(target=_run_llm_server, args=(llm_port,))
        llm_proc.start()
        started_processes.append(llm_proc)
        _write_pid_file(args.pid_output, started_processes)
        wait_for_server(llm_url, timeout=10, endpoint="/test/stats")
        print("[E2E Services] Mock LLM server ready")

        # Start mock agent
        scenario = args.scenario
        agent_proc = multiprocessing.Process(
            target=_run_agent_server, args=(agent_port, scenario)
        )
        agent_proc.start()
        started_processes.append(agent_proc)
        _write_pid_file(args.pid_output, started_processes)
        wait_for_server(agent_url, timeout=10, endpoint="/test/commands")
        print("[E2E Services] Mock agent server ready")

        # Start AutoGLM-GUI backend
        print(f"[E2E Services] Starting backend process with coverage={args.coverage}")
        backend_proc = multiprocessing.Process(
            target=_run_autoglm_server, args=(backend_port, llm_url)
        )
        backend_proc.start()
        started_processes.append(backend_proc)
        _write_pid_file(args.pid_output, started_processes)
        print(f"[E2E Services] Backend process started pid={backend_proc.pid}")
        wait_for_server(backend_url, timeout=60, endpoint="/api/health")
        print("[E2E Services] AutoGLM-GUI backend ready")
    except Exception:
        _terminate_processes(started_processes)
        if os.path.exists(output_path):
            os.remove(output_path)
        if args.pid_output and os.path.exists(args.pid_output):
            os.remove(args.pid_output)
        raise

    # Write URLs file for Playwright
    urls = {
        "llm_url": llm_url,
        "agent_url": agent_url,
        "backend_url": backend_url,
        "frontend_url": "http://localhost:3000",
    }
    with open(output_path, "w") as f:
        json.dump(urls, f)
    print(f"[E2E Services] URLs written to {output_path}")

    # Wait for termination
    _shutting_down = False

    def cleanup(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return
        _shutting_down = True
        print("\n[E2E Services] Shutting down...")
        _terminate_processes(started_processes)
        if os.path.exists(output_path):
            os.remove(output_path)
        if args.pid_output and os.path.exists(args.pid_output):
            os.remove(args.pid_output)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Block until any child dies (which would be unexpected)
    while all(p.is_alive() for p in started_processes):
        time.sleep(1)

    # If we get here, a child died unexpectedly
    print("[E2E Services] ERROR: A service died unexpectedly!")
    cleanup(None, None)


if __name__ == "__main__":
    main()
