"""ADB-only interactive REPL used by the web terminal."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys


def _resolve_adb_binary() -> str:
    return os.environ.get("AUTOGLM_ADB_PATH", "adb")


def _print_banner() -> None:
    print("AutoGLM Web Terminal (ADB-only mode)", flush=True)
    print("Allowed commands: adb ...", flush=True)
    print("Built-ins: help, clear, exit, quit", flush=True)
    print("", flush=True)


def _handle_builtin(command: str) -> bool:
    if command in {"exit", "quit"}:
        raise EOFError
    if command in {"help", "?"}:
        _print_banner()
        return True
    if command == "clear":
        print("\033[2J\033[H", end="", flush=True)
        return True
    return False


def _run_adb_command(line: str) -> None:
    try:
        args = shlex.split(line)
    except ValueError as exc:
        print(f"Parse error: {exc}", flush=True)
        return

    if not args:
        return

    if _handle_builtin(args[0]):
        return

    if args[0] != "adb":
        print("Only adb commands are allowed.", flush=True)
        return

    args[0] = _resolve_adb_binary()

    try:
        completed = subprocess.run(args, check=False)
    except FileNotFoundError:
        print(f"ADB binary not found: {args[0]}", flush=True)
        return
    except KeyboardInterrupt:
        print("^C", flush=True)
        return

    if completed.returncode != 0:
        print(f"[exit code {completed.returncode}]", flush=True)


def main() -> int:
    _print_banner()

    while True:
        try:
            line = input("adb> ").strip()
        except EOFError:
            print("", flush=True)
            return 0
        except KeyboardInterrupt:
            print("^C", flush=True)
            continue

        if not line:
            continue

        try:
            _run_adb_command(line)
        except EOFError:
            return 0


if __name__ == "__main__":
    sys.exit(main())
