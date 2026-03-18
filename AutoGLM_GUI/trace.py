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

_FALSE_VALUES = {"0", "false", "no", "off"}


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
    current_time = now or datetime.now()
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
    "create_trace_id",
    "current_span_id",
    "current_trace_id",
    "summarize_text",
    "trace_context",
    "trace_enabled",
    "trace_sleep",
    "trace_span",
]
