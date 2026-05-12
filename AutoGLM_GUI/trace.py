"""Lightweight span-based tracing for execution latency analysis."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal


_TRACE_ID: ContextVar[str | None] = ContextVar("autoglm_trace_id", default=None)
_SPAN_STACK: ContextVar[tuple[str, ...]] = ContextVar(
    "autoglm_trace_span_stack", default=()
)
_WRITE_LOCK = threading.Lock()
_TRACE_STATE_LOCK = threading.Lock()
_TRACE_COLLECTORS: dict[str, "_TraceCollector"] = {}

_FALSE_VALUES = {"0", "false", "no", "off"}
_STEP_TIMING_FIELDS = (
    "total_duration_ms",
    "screenshot_duration_ms",
    "current_app_duration_ms",
    "llm_duration_ms",
    "parse_action_duration_ms",
    "execute_action_duration_ms",
    "update_context_duration_ms",
    "adb_duration_ms",
    "sleep_duration_ms",
    "other_duration_ms",
)


def trace_enabled() -> bool:
    """Return whether trace logging is enabled."""
    return os.getenv("AUTOGLM_TRACE_ENABLED", "1").strip().lower() not in _FALSE_VALUES


def create_trace_id() -> str:
    """Create a new trace identifier."""
    return uuid.uuid4().hex


def current_trace_id() -> str | None:
    """Return the active trace identifier."""
    return _TRACE_ID.get()


def current_span_id() -> str | None:
    """Return the current span identifier."""
    stack = _SPAN_STACK.get()
    return stack[-1] if stack else None


def summarize_text(text: str | None, limit: int = 160) -> str | None:
    """Compact text for trace attributes."""
    if text is None:
        return None

    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _resolve_trace_path(now: datetime | None = None) -> Path:
    current_time = now or datetime.now(tz=timezone.utc)
    template = os.getenv("AUTOGLM_TRACE_FILE", "logs/trace_{date}.jsonl")
    path = Path(template.format(date=current_time.strftime("%Y-%m-%d")))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_attr_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return summarize_text(value, limit=512)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_normalize_attr_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_attr_value(val) for key, val in value.items()}
    return summarize_text(str(value), limit=512)


def _normalize_attrs(attrs: dict[str, Any] | None) -> dict[str, Any]:
    if not attrs:
        return {}
    return {str(key): _normalize_attr_value(value) for key, value in attrs.items()}


def _write_trace_record(record: dict[str, Any]) -> None:
    if not trace_enabled():
        return

    path = _resolve_trace_path()
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")


def _extract_step(attrs: dict[str, Any]) -> int | None:
    raw_step = attrs.get("step")
    if isinstance(raw_step, bool):
        return None
    if isinstance(raw_step, int):
        return raw_step
    if isinstance(raw_step, str) and raw_step.isdigit():
        return int(raw_step)
    return None


def _categorize_step_span(name: str) -> str | None:
    if name == "step.capture_screenshot":
        return "screenshot_duration_ms"
    if name == "step.get_current_app":
        return "current_app_duration_ms"
    if name == "step.llm":
        return "llm_duration_ms"
    if name == "step.parse_action":
        return "parse_action_duration_ms"
    if name == "step.execute_action":
        return "execute_action_duration_ms"
    if name == "step.update_context":
        return "update_context_duration_ms"
    if name.startswith("step."):
        return "other_duration_ms"
    return None


def _is_adb_breakdown_span(name: str) -> bool:
    if not name.startswith("adb."):
        return False
    return name not in {
        "adb.capture_screenshot",
        "adb.exec_out_screencap",
        "adb.get_current_app",
    }


@dataclass
class _ActiveSpanState:
    name: str
    attrs: dict[str, Any]
    parent_span_id: str | None
    start_perf_ns: int


@dataclass
class _MutableStepTimingSummary:
    total_duration_ms: float = 0.0
    screenshot_duration_ms: float = 0.0
    current_app_duration_ms: float = 0.0
    llm_duration_ms: float = 0.0
    parse_action_duration_ms: float = 0.0
    execute_action_duration_ms: float = 0.0
    update_context_duration_ms: float = 0.0
    adb_duration_ms: float = 0.0
    sleep_duration_ms: float = 0.0
    other_duration_ms: float = 0.0

    def add_duration(self, field_name: str, duration_ms: float) -> None:
        setattr(self, field_name, getattr(self, field_name) + duration_ms)

    def to_dict(
        self,
        *,
        trace_id: str,
        step: int,
        active_step_start_ns: int | None = None,
    ) -> dict[str, Any]:
        total_duration_ms = self.total_duration_ms
        if active_step_start_ns is not None:
            live_total = (time.perf_counter_ns() - active_step_start_ns) / 1e6
            total_duration_ms = max(total_duration_ms, live_total)

        return {
            "step": step,
            "trace_id": trace_id,
            "total_duration_ms": round(total_duration_ms, 3),
            "screenshot_duration_ms": round(self.screenshot_duration_ms, 3),
            "current_app_duration_ms": round(self.current_app_duration_ms, 3),
            "llm_duration_ms": round(self.llm_duration_ms, 3),
            "parse_action_duration_ms": round(self.parse_action_duration_ms, 3),
            "execute_action_duration_ms": round(self.execute_action_duration_ms, 3),
            "update_context_duration_ms": round(self.update_context_duration_ms, 3),
            "adb_duration_ms": round(self.adb_duration_ms, 3),
            "sleep_duration_ms": round(self.sleep_duration_ms, 3),
            "other_duration_ms": round(self.other_duration_ms, 3),
        }


@dataclass
class _TraceCollector:
    trace_id: str
    active_spans: dict[str, _ActiveSpanState] = field(default_factory=dict)
    step_summaries: dict[int, _MutableStepTimingSummary] = field(default_factory=dict)
    active_step_starts: dict[int, int] = field(default_factory=dict)

    def register_span_start(
        self,
        *,
        span_id: str,
        name: str,
        attrs: dict[str, Any],
        parent_span_id: str | None,
        start_perf_ns: int,
    ) -> None:
        self.active_spans[span_id] = _ActiveSpanState(
            name=name,
            attrs=attrs,
            parent_span_id=parent_span_id,
            start_perf_ns=start_perf_ns,
        )

        step = _extract_step(attrs)
        if name == "agent.step" and step is not None:
            self.active_step_starts[step] = start_perf_ns

    def register_span_end(self, *, span_id: str, duration_ms: float) -> None:
        active_span = self.active_spans.pop(span_id, None)
        if active_span is None:
            return

        step = self._resolve_step(active_span)
        if step is None:
            return

        summary = self.step_summaries.setdefault(step, _MutableStepTimingSummary())

        if active_span.name == "agent.step":
            summary.total_duration_ms = max(summary.total_duration_ms, duration_ms)
            self.active_step_starts.pop(step, None)
            return

        step_field = _categorize_step_span(active_span.name)
        if step_field is not None:
            summary.add_duration(step_field, duration_ms)

        if active_span.name.startswith("sleep."):
            summary.add_duration("sleep_duration_ms", duration_ms)

        if _is_adb_breakdown_span(active_span.name):
            summary.add_duration("adb_duration_ms", duration_ms)

    def get_step_summary(self, step: int) -> dict[str, Any] | None:
        summary = self.step_summaries.get(step)
        active_step_start_ns = self.active_step_starts.get(step)
        if summary is None and active_step_start_ns is None:
            return None

        summary = summary or _MutableStepTimingSummary()
        return summary.to_dict(
            trace_id=self.trace_id,
            step=step,
            active_step_start_ns=active_step_start_ns,
        )

    def list_step_summaries(self) -> list[dict[str, Any]]:
        step_numbers = sorted(set(self.step_summaries) | set(self.active_step_starts))
        return [
            summary
            for step in step_numbers
            if (summary := self.get_step_summary(step)) is not None
        ]

    def build_trace_summary(
        self,
        *,
        total_duration_ms: float | None = None,
        steps: int | None = None,
    ) -> dict[str, Any] | None:
        step_summaries = self.list_step_summaries()
        if not step_summaries and total_duration_ms is None and steps is None:
            return None

        totals = {metric: 0.0 for metric in _STEP_TIMING_FIELDS}
        for summary in step_summaries:
            for metric in _STEP_TIMING_FIELDS:
                totals[metric] += float(summary.get(metric, 0.0))

        if total_duration_ms is not None:
            totals["total_duration_ms"] = total_duration_ms

        return {
            "trace_id": self.trace_id,
            "steps": steps if steps is not None else len(step_summaries),
            **{field: round(value, 3) for field, value in totals.items()},
        }

    def _resolve_step(self, active_span: _ActiveSpanState) -> int | None:
        direct_step = _extract_step(active_span.attrs)
        if direct_step is not None:
            return direct_step

        parent_span_id = active_span.parent_span_id
        while parent_span_id is not None:
            parent_span = self.active_spans.get(parent_span_id)
            if parent_span is None:
                return None
            parent_step = _extract_step(parent_span.attrs)
            if parent_step is not None:
                return parent_step
            parent_span_id = parent_span.parent_span_id

        return None


def _get_trace_collector(
    trace_id: str, *, create: bool = False
) -> _TraceCollector | None:
    collector = _TRACE_COLLECTORS.get(trace_id)
    if collector is None and create:
        collector = _TraceCollector(trace_id=trace_id)
        _TRACE_COLLECTORS[trace_id] = collector
    return collector


def get_step_timing_summary(
    step: int, *, trace_id: str | None = None
) -> dict[str, Any] | None:
    """Return the current timing summary for a step in the active trace."""
    active_trace_id = trace_id or current_trace_id()
    if active_trace_id is None:
        return None

    with _TRACE_STATE_LOCK:
        collector = _get_trace_collector(active_trace_id)
        if collector is None:
            return None
        return collector.get_step_summary(step)


def list_step_timing_summaries(*, trace_id: str | None = None) -> list[dict[str, Any]]:
    """Return all known step timing summaries for a trace."""
    active_trace_id = trace_id or current_trace_id()
    if active_trace_id is None:
        return []

    with _TRACE_STATE_LOCK:
        collector = _get_trace_collector(active_trace_id)
        if collector is None:
            return []
        return collector.list_step_summaries()


def get_trace_timing_summary(
    *,
    trace_id: str | None = None,
    total_duration_ms: float | None = None,
    steps: int | None = None,
) -> dict[str, Any] | None:
    """Return the aggregate timing summary for a trace."""
    active_trace_id = trace_id or current_trace_id()
    if active_trace_id is None:
        return None

    with _TRACE_STATE_LOCK:
        collector = _get_trace_collector(active_trace_id)
        if collector is None:
            return None
        return collector.build_trace_summary(
            total_duration_ms=total_duration_ms,
            steps=steps,
        )


def clear_trace_data(trace_id: str | None = None) -> None:
    """Remove in-memory timing data for a trace."""
    active_trace_id = trace_id or current_trace_id()
    if active_trace_id is None:
        return

    with _TRACE_STATE_LOCK:
        _TRACE_COLLECTORS.pop(active_trace_id, None)


@contextmanager
def trace_context(trace_id: str, reset_stack: bool = True) -> Iterator[None]:
    """Temporarily bind a trace id to the current execution context."""
    trace_token = _TRACE_ID.set(trace_id)
    stack_token: Token[tuple[str, ...]] | None = None
    if reset_stack:
        stack_token = _SPAN_STACK.set(())

    try:
        yield
    finally:
        if stack_token is not None:
            _SPAN_STACK.reset(stack_token)
        _TRACE_ID.reset(trace_token)


@dataclass
class TraceSpan:
    """Context manager for a single trace span."""

    name: str
    attrs: dict[str, Any] = field(default_factory=dict)
    new_trace: bool = False

    trace_id: str | None = field(init=False, default=None)
    span_id: str | None = field(init=False, default=None)
    parent_span_id: str | None = field(init=False, default=None)

    _enabled: bool = field(init=False, default=False)
    _start_wall_time: datetime | None = field(init=False, default=None)
    _start_perf_ns: int | None = field(init=False, default=None)
    _trace_token: Token[str | None] | None = field(init=False, default=None)
    _stack_token: Token[tuple[str, ...]] | None = field(init=False, default=None)

    def __enter__(self) -> TraceSpan:
        self._enabled = trace_enabled()
        if not self._enabled:
            return self

        active_trace_id = _TRACE_ID.get()
        if self.new_trace or active_trace_id is None:
            active_trace_id = create_trace_id()
            self._trace_token = _TRACE_ID.set(active_trace_id)

        self.trace_id = active_trace_id
        self.span_id = uuid.uuid4().hex[:16]

        stack = _SPAN_STACK.get()
        self.parent_span_id = stack[-1] if stack else None
        self._stack_token = _SPAN_STACK.set((*stack, self.span_id))

        self._start_wall_time = datetime.now(timezone.utc)
        self._start_perf_ns = time.perf_counter_ns()
        with _TRACE_STATE_LOCK:
            collector = _get_trace_collector(self.trace_id, create=True)
            if collector is not None:
                collector.register_span_start(
                    span_id=self.span_id,
                    name=self.name,
                    attrs=self.attrs,
                    parent_span_id=self.parent_span_id,
                    start_perf_ns=self._start_perf_ns,
                )
        return self

    def set_attribute(self, key: str, value: Any) -> None:
        """Set or update a span attribute."""
        self.attrs[str(key)] = value

    def set_attributes(self, attrs: dict[str, Any]) -> None:
        """Set multiple span attributes."""
        self.attrs.update(attrs)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> Literal[False]:
        try:
            if self._enabled and self.trace_id and self.span_id:
                end_time = datetime.now(timezone.utc)
                duration_ms = 0.0
                if self._start_perf_ns is not None:
                    duration_ms = (time.perf_counter_ns() - self._start_perf_ns) / 1e6

                with _TRACE_STATE_LOCK:
                    collector = _get_trace_collector(self.trace_id)
                    if collector is not None:
                        collector.register_span_end(
                            span_id=self.span_id,
                            duration_ms=duration_ms,
                        )

                record: dict[str, Any] = {
                    "trace_id": self.trace_id,
                    "span_id": self.span_id,
                    "parent_span_id": self.parent_span_id,
                    "name": self.name,
                    "status": "error" if exc_type else "ok",
                    "start_time": self._start_wall_time.isoformat()
                    if self._start_wall_time is not None
                    else None,
                    "end_time": end_time.isoformat(),
                    "duration_ms": round(duration_ms, 3),
                    "attrs": _normalize_attrs(self.attrs),
                }

                if exc_type is not None:
                    record["error"] = {
                        "type": exc_type.__name__,
                        "message": summarize_text(str(exc_value), limit=1024),
                    }

                _write_trace_record(record)
        finally:
            if self._stack_token is not None:
                _SPAN_STACK.reset(self._stack_token)
            if self._trace_token is not None:
                _TRACE_ID.reset(self._trace_token)

        return False


def trace_span(
    name: str,
    attrs: dict[str, Any] | None = None,
    *,
    new_trace: bool = False,
) -> TraceSpan:
    """Create a trace span context manager."""
    return TraceSpan(name=name, attrs=attrs or {}, new_trace=new_trace)


def trace_sleep(
    duration_seconds: float,
    *,
    name: str = "sleep",
    attrs: dict[str, Any] | None = None,
) -> None:
    """Sleep while recording a dedicated trace span."""
    safe_duration = max(duration_seconds, 0.0)
    span_attrs = {"duration_ms": round(safe_duration * 1000, 3)}
    if attrs:
        span_attrs.update(attrs)

    with trace_span(name, attrs=span_attrs):
        time.sleep(safe_duration)


__all__ = [
    "TraceSpan",
    "clear_trace_data",
    "create_trace_id",
    "current_span_id",
    "current_trace_id",
    "get_step_timing_summary",
    "get_trace_timing_summary",
    "list_step_timing_summaries",
    "summarize_text",
    "trace_context",
    "trace_enabled",
    "trace_sleep",
    "trace_span",
]
