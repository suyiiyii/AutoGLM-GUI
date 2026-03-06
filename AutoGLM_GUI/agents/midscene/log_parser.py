"""Midscene CLI debug output parser.

Parses lines from ``DEBUG=midscene:*`` stdout to extract structured events:
- AI reasoning (deep thinking)
- planResult JSON (complete step data: thought + action + subGoals)
- Task finished message (final result, may span multiple lines)
- Action executing notification
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maximum lines to accumulate before giving up on a JSON block
_MAX_JSON_LINES = 200

# Prefixes that indicate a new log entry (not continuation of previous content)
_LOG_ENTRY_PREFIXES = (
    "dbug ",
    "info ",
    "Action ",
    "Midscene ",
    "Screenshot ",
    "Connected ",
    "Disconnected ",
    "npm ",
)


class MidsceneLogParser:
    """Stateful line-by-line parser for Midscene debug output.

    Usage::

        parser = MidsceneLogParser()
        for line in process_stdout:
            for event in parser.feed(line):
                handle(event)
        # After EOF, flush any pending state:
        for event in parser.flush():
            handle(event)
    """

    def __init__(self) -> None:
        self._json_lines: list[str] | None = None
        self._task_msg_lines: list[str] | None = None

    def feed(self, raw_line: str) -> list[dict[str, Any]]:
        """Feed one line of output.  Returns zero or more parsed events."""
        line = raw_line.rstrip("\n\r")
        events: list[dict[str, Any]] = []

        # ---- JSON accumulation mode ----
        if self._json_lines is not None:
            if _is_new_log_entry(line):
                self._try_parse_json(events)
                # Fall through to process this line normally
            else:
                self._json_lines.append(line)
                if len(self._json_lines) > _MAX_JSON_LINES:
                    logger.warning("[MidsceneParser] JSON block too long, giving up")
                    self._json_lines = None
                    return events
                self._try_parse_json(events)
                return events

        # ---- Task message accumulation mode ----
        if self._task_msg_lines is not None:
            if _is_new_log_entry(line):
                # This line is a new log entry → the message is complete
                self._flush_task_message(events)
                # Fall through to process this line normally
            else:
                # Continuation of the multi-line message
                self._task_msg_lines.append(line)
                return events

        # ---- Strip timestamp prefix ----
        content = _strip_timestamp(line)

        # ---- planResult start (triggers JSON accumulation) ----
        if "midscene:device-task-executor planResult" in content:
            idx = content.find("{")
            if idx != -1:
                json_start = content[idx:]
                self._json_lines = [json_start]
                self._try_parse_json(events)
            return events

        # ---- AI deep reasoning ----
        marker = "midscene:ai:call response reasoning content: "
        if marker in content:
            idx = content.index(marker) + len(marker)
            events.append({"event": "reasoning", "data": content[idx:]})
            return events

        # ---- Action executing ----
        marker = "midscene:agent:task-builder calling action "
        if marker in content:
            idx = content.index(marker) + len(marker)
            events.append({"event": "action_executing", "data": content[idx:]})
            return events

        # ---- Task finished (may be multi-line) ----
        if line.startswith("Task finished, message: "):
            first_line = line[len("Task finished, message: ") :]
            self._task_msg_lines = [first_line]
            return events

        return events

    def flush(self) -> list[dict[str, Any]]:
        """Flush any pending state (call after EOF)."""
        events: list[dict[str, Any]] = []
        self._try_parse_json(events)
        self._flush_task_message(events)
        return events

    def _try_parse_json(self, events: list[dict[str, Any]]) -> None:
        """Attempt to parse accumulated lines as JSON.  Clear state on success."""
        if self._json_lines is None:
            return
        json_text = "\n".join(self._json_lines)
        try:
            data = json.loads(json_text)
        except (json.JSONDecodeError, ValueError):
            return  # Not complete yet, keep accumulating
        self._json_lines = None
        if isinstance(data, dict):
            events.append({"event": "plan_result", "data": data})

    def _flush_task_message(self, events: list[dict[str, Any]]) -> None:
        """Emit the accumulated task_finished message."""
        if self._task_msg_lines is None:
            return
        msg = "\n".join(self._task_msg_lines)
        self._task_msg_lines = None
        events.append({"event": "task_finished", "data": msg})


def _is_new_log_entry(line: str) -> bool:
    """Check if a line is a new timestamped debug log entry."""
    if len(line) > 25 and line[4] == "-" and line[10] == "T" and line[23] == "Z":
        return True
    if line.startswith(_LOG_ENTRY_PREFIXES):
        return True
    return False


def _strip_timestamp(line: str) -> str:
    """Remove the ``YYYY-MM-DDTHH:MM:SS.mmmZ `` prefix if present."""
    if len(line) > 25 and line[4] == "-" and line[10] == "T" and line[23] == "Z":
        return line[25:]
    return line
