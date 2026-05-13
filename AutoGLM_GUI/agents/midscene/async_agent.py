"""AsyncMidsceneAgent - Midscene.js CLI integration adapter.

Wraps ``npx @midscene/android@1`` as an AsyncAgent.  Midscene manages its own
ADB connection and uses vision-language models for pure-visual UI automation.

Prerequisites:
- Node.js / npx available in PATH
- A vision model configured (Doubao, Qwen, Gemini, etc.)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from collections.abc import AsyncGenerator
from typing import Any

from AutoGLM_GUI.config import AgentConfig, ModelConfig
from AutoGLM_GUI.logger import logger

from .log_parser import MidsceneLogParser


class AsyncMidsceneAgent:
    """Midscene Agent adapter implementing the AsyncAgent Protocol.

    Launches ``npx @midscene/android@1`` as a subprocess with
    ``DEBUG=midscene:*`` and parses the debug output to produce
    a standard event stream (thinking / step / done / error / cancelled).
    """

    def __init__(
        self,
        model_config: ModelConfig,
        agent_config: AgentConfig,
        device: Any,
        takeover_callback: Any = None,  # noqa: ARG002
        confirmation_callback: Any = None,  # noqa: ARG002
    ) -> None:
        self.model_config = model_config
        self.agent_config = agent_config
        self._device = device
        self._step_count = 0
        self._cancel_event = asyncio.Event()
        self._process: asyncio.subprocess.Process | None = None

    # ------------------------------------------------------------------
    # AsyncAgent Protocol
    # ------------------------------------------------------------------

    async def stream(self, task: str) -> AsyncGenerator[dict[str, Any], None]:
        """Execute *task* via Midscene CLI, yielding standard events."""
        self._step_count = 0
        self._cancel_event.clear()

        # --- Preflight: check npx availability ---
        npx_path = self._find_npx()
        if npx_path is None:
            yield {
                "type": "error",
                "data": {
                    "message": (
                        "未检测到 npx 命令，请先安装 Node.js。\n"
                        "macOS: brew install node\n"
                        "https://nodejs.org/"
                    )
                },
            }
            return

        yield {
            "type": "thinking",
            "data": {
                "chunk": (
                    "[Midscene 模式] 正在启动 Midscene 视觉 Agent…\n"
                    "需要 Node.js 环境和视觉模型 API。"
                ),
            },
        }

        # --- Build environment variables ---
        env = self._build_env()
        device_id = self._get_device_id()
        work_dir = tempfile.mkdtemp(prefix="midscene_")

        try:
            # --- Phase 1: Connect ---
            yield {
                "type": "thinking",
                "data": {"chunk": f"正在连接设备 {device_id}…"},
            }
            connect_args = [npx_path, "--yes", "@midscene/android@1", "connect"]
            if device_id:
                connect_args.extend(["--deviceId", device_id])

            ok, output = await self._run_command(
                connect_args, env, work_dir, timeout=120
            )
            if not ok:
                yield {
                    "type": "error",
                    "data": {"message": f"Midscene 连接设备失败：\n{output}"},
                }
                return

            if self._cancel_event.is_set():
                yield {"type": "cancelled", "data": {"message": "任务已取消"}}
                return

            # --- Phase 2: Act (main execution with streaming parse) ---
            yield {
                "type": "thinking",
                "data": {"chunk": f"开始执行任务：{task}"},
            }

            act_args = [
                npx_path,
                "--yes",
                "@midscene/android@1",
                "act",
                "--prompt",
                task,
            ]
            async for event in self._run_act_streaming(act_args, env, work_dir):
                yield event
                if event["type"] in ("error", "cancelled", "done"):
                    return

            # If we didn't get a done event from parsing, synthesize one
            if self._step_count > 0:
                yield {
                    "type": "done",
                    "data": {
                        "message": "Midscene 任务执行完毕",
                        "steps": self._step_count,
                        "success": True,
                    },
                }

        finally:
            # --- Phase 3: Disconnect (best-effort) ---
            await self._run_command(
                [npx_path, "--yes", "@midscene/android@1", "disconnect"],
                env,
                work_dir,
                timeout=30,
            )
            # Clean up temp dir
            try:
                os.rmdir(work_dir)
            except OSError:
                pass

    async def cancel(self) -> None:
        """Cancel the current execution."""
        self._cancel_event.set()
        if self._process is not None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass

    async def run(self, task: str) -> str:
        """Run the full task, return final message."""
        result = ""
        async for event in self.stream(task):
            if event.get("type") == "done":
                result = event.get("data", {}).get("message", "")
        return result

    def reset(self) -> None:
        """Reset state."""
        self._cancel_event.clear()
        self._step_count = 0
        self._process = None

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def context(self) -> list[dict[str, Any]]:
        return []

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    _shell_path_cache: str | None = None

    @classmethod
    def _get_shell_path(cls) -> str:
        """Load the user's login shell PATH and cache the result.

        On macOS, GUI apps (Electron / Finder / Dock) inherit a minimal
        PATH (``/usr/bin:/bin:/usr/sbin:/sbin``) because shell profile
        files (``.zshrc``, ``.bash_profile``) are never sourced.  This
        method spawns a login shell once to retrieve the full PATH, then
        caches it for the lifetime of the process.
        """
        if cls._shell_path_cache is not None:
            return cls._shell_path_cache

        current_path = os.environ.get("PATH", "")
        try:
            user_shell = os.environ.get("SHELL", "/bin/zsh")
            result = subprocess.run(
                [user_shell, "-l", "-c", "echo $PATH"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                cls._shell_path_cache = result.stdout.strip()
                logger.info(f"[Midscene] Loaded shell PATH from {user_shell}")
                return cls._shell_path_cache
        except Exception as e:
            logger.warning(f"[Midscene] Failed to load shell PATH: {e}")

        cls._shell_path_cache = current_path
        return cls._shell_path_cache

    @classmethod
    def _find_npx(cls) -> str | None:
        """Locate the ``npx`` binary using the user's full shell PATH."""
        shell_path = cls._get_shell_path()
        return shutil.which("npx", path=shell_path)

    def _get_device_id(self) -> str:
        """Extract device ID from device object."""
        if hasattr(self._device, "device_id"):
            return self._device.device_id
        return ""

    def _build_env(self) -> dict[str, str]:
        """Build environment variables for the Midscene subprocess."""
        env = os.environ.copy()
        # Use the full shell PATH so the subprocess can find Node.js, npx,
        # and other tools even when launched from a GUI (Electron / Finder).
        env["PATH"] = self._get_shell_path()
        # Enable full debug output for parsing
        env["DEBUG"] = "midscene:*"
        # Disable color codes in debug output for cleaner parsing
        env["DEBUG_COLORS"] = "false"
        # Map model config to Midscene env vars
        if self.model_config.api_key:
            env["MIDSCENE_MODEL_API_KEY"] = self.model_config.api_key
        if self.model_config.base_url:
            env["MIDSCENE_MODEL_BASE_URL"] = self.model_config.base_url
        if self.model_config.model_name:
            env["MIDSCENE_MODEL_NAME"] = self.model_config.model_name
        # Model family from extra_body or agent_config
        model_family = self.model_config.extra_body.get("model_family", "")
        if model_family:
            env["MIDSCENE_MODEL_FAMILY"] = model_family
        # Replanning cycle limit from max_steps
        env["MIDSCENE_REPLANNING_CYCLE_LIMIT"] = str(self.agent_config.max_steps)
        # Ensure ANDROID_HOME is set (required by appium-adb inside Midscene)
        if not env.get("ANDROID_HOME"):
            android_home = self._detect_android_home()
            if android_home:
                env["ANDROID_HOME"] = android_home
                env.setdefault("ANDROID_SDK_ROOT", android_home)
        return env

    @staticmethod
    def _detect_android_home() -> str:
        """Auto-detect ANDROID_HOME from the adb binary location."""
        adb_path = shutil.which("adb")
        if adb_path:
            # adb is typically at <ANDROID_HOME>/platform-tools/adb
            real_path = os.path.realpath(adb_path)
            platform_tools = os.path.dirname(real_path)
            if os.path.basename(platform_tools) == "platform-tools":
                return os.path.dirname(platform_tools)
            # Fallback: just use the directory containing adb
            return platform_tools
        return ""

    async def _run_command(
        self,
        args: list[str],
        env: dict[str, str],
        cwd: str,
        timeout: int = 60,
    ) -> tuple[bool, str]:
        """Run a simple Midscene command and return (success, output)."""
        cmd_str = " ".join(args)
        logger.info(f"[Midscene] Running command: {cmd_str}")
        logger.debug(f"[Midscene] cwd={cwd}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            output = (
                stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            )
            logger.info(f"[Midscene] Command exited with code {proc.returncode}")
            if proc.returncode != 0:
                logger.error(f"[Midscene] Command failed:\n{output}")
            else:
                logger.debug(f"[Midscene] Command output:\n{output[-500:]}")
            return proc.returncode == 0, output
        except asyncio.TimeoutError:
            logger.error(f"[Midscene] Command timed out after {timeout}s: {cmd_str}")
            return False, "命令执行超时"
        except Exception as e:
            logger.error(f"[Midscene] Command exception: {e}")
            return False, str(e)

    async def _run_act_streaming(
        self,
        args: list[str],
        env: dict[str, str],
        cwd: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the ``act`` command and stream parsed events."""
        cmd_str = " ".join(args)
        logger.info(f"[Midscene] Starting streaming act: {cmd_str}")
        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )
        except Exception as e:
            logger.error(f"[Midscene] Failed to start act process: {e}")
            yield {"type": "error", "data": {"message": f"启动 Midscene 失败：{e}"}}
            return

        parser = MidsceneLogParser()
        task_message: str | None = None
        # Collect all output lines for error reporting
        all_output_lines: list[str] = []

        try:
            assert self._process.stdout is not None
            while True:
                # Check cancellation
                if self._cancel_event.is_set():
                    self._process.terminate()
                    yield {"type": "cancelled", "data": {"message": "任务已取消"}}
                    return

                try:
                    line_bytes = await asyncio.wait_for(
                        self._process.stdout.readline(), timeout=300
                    )
                except asyncio.TimeoutError:
                    self._process.terminate()
                    logger.error("[Midscene] Act process timed out (5min no output)")
                    yield {
                        "type": "error",
                        "data": {"message": "Midscene 执行超时 (5分钟无输出)"},
                    }
                    return

                if not line_bytes:
                    break  # EOF

                line = line_bytes.decode("utf-8", errors="replace")
                stripped = line.rstrip("\n\r")
                if stripped:
                    all_output_lines.append(stripped)
                    logger.debug(f"[Midscene] | {stripped}")

                for event in parser.feed(line):
                    ev_type = event["event"]

                    if ev_type == "reasoning":
                        yield {
                            "type": "thinking",
                            "data": {"chunk": event["data"]},
                        }

                    elif ev_type == "plan_result":
                        plan = event.get("data")
                        if not isinstance(plan, dict):
                            logger.warning(
                                f"[Midscene] Skipping invalid planResult: {type(plan)}"
                            )
                            continue
                        self._step_count += 1
                        action = plan.get("action") or {}
                        action_type = (
                            action.get("type", "unknown")
                            if isinstance(action, dict)
                            else str(action)
                        )
                        thought = plan.get("thought", "")
                        log_msg = plan.get("log", "")
                        logger.info(
                            f"[Midscene] Step {self._step_count}: "
                            f"action={action_type}, "
                            f"thought={thought[:80]}"
                        )

                        action_display: dict[str, Any] = {
                            "_metadata": "Midscene",
                            "type": action_type,
                            "description": log_msg,
                        }
                        if isinstance(action, dict) and action.get("param"):
                            action_display["param"] = action["param"]

                        yield {
                            "type": "step",
                            "data": {
                                "step": self._step_count,
                                "thinking": thought,
                                "action": action_display,
                                "success": True,
                                "finished": not plan.get(
                                    "shouldContinuePlanning", True
                                ),
                                "message": log_msg,
                            },
                        }

                    elif ev_type == "task_finished":
                        task_message = str(event["data"])
                        logger.info(f"[Midscene] Task finished: {task_message[:100]}")

                    elif ev_type == "action_executing":
                        yield {
                            "type": "thinking",
                            "data": {
                                "chunk": f"正在执行操作: {event['data']}",
                            },
                        }

            # Flush any pending parser state (e.g. multi-line task message)
            for event in parser.flush():
                ev_type = event["event"]
                if ev_type == "task_finished":
                    task_message = str(event["data"])
                    logger.info(f"[Midscene] Task finished: {task_message[:200]}")

            # Wait for process exit
            await self._process.wait()
            exit_code = self._process.returncode or 0
            logger.info(f"[Midscene] Act process exited with code {exit_code}")

            if task_message is not None:
                yield {
                    "type": "done",
                    "data": {
                        "message": task_message,
                        "steps": self._step_count,
                        "success": True,
                    },
                }
            elif exit_code != 0:
                # Extract error lines from output for user-facing message
                error_lines = [
                    line
                    for line in all_output_lines
                    if any(k in line.lower() for k in ("error", "failed", "unable"))
                ]
                error_detail = (
                    "\n".join(error_lines[-5:]) if error_lines else "未知错误"
                )
                full_msg = f"Midscene 执行失败 (code={exit_code})：\n{error_detail}"
                logger.error(
                    "[Midscene] Act failed. Last 20 lines:\n"
                    + "\n".join(all_output_lines[-20:])
                )
                yield {
                    "type": "error",
                    "data": {"message": full_msg},
                }

        except Exception as e:
            logger.error(f"[Midscene] Streaming parse error: {e}")
            yield {"type": "error", "data": {"message": f"执行错误：{e}"}}
        finally:
            self._process = None
