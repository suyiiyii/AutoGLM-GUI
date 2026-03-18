"""Tests for lightweight trace spans."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from AutoGLM_GUI.trace import (
    current_trace_id,
    trace_context,
    trace_sleep,
    trace_span,
)


def _read_trace_records(trace_file: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in trace_file.read_text().splitlines()]


def test_trace_span_writes_nested_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with trace_span("parent", new_trace=True) as parent_span:
        with trace_span("child", attrs={"value": 1, "path": Path("/tmp/demo")}):
            trace_sleep(0, name="sleep.test")

    records = _read_trace_records(trace_file)

    assert len(records) == 3

    child_record = next(record for record in records if record["name"] == "child")
    parent_record = next(record for record in records if record["name"] == "parent")
    sleep_record = next(record for record in records if record["name"] == "sleep.test")

    assert child_record["trace_id"] == parent_record["trace_id"]
    assert child_record["parent_span_id"] == parent_span.span_id
    assert sleep_record["parent_span_id"] == child_record["span_id"]
    assert child_record["attrs"] == {"path": "/tmp/demo", "value": 1}


def test_trace_context_sets_trace_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with trace_context("trace-123"):
        assert current_trace_id() == "trace-123"
        with trace_span("inside-context"):
            pass

    records = _read_trace_records(trace_file)
    assert records[0]["trace_id"] == "trace-123"


def test_trace_span_records_error_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trace_file = tmp_path / "trace.jsonl"
    monkeypatch.setenv("AUTOGLM_TRACE_FILE", str(trace_file))
    monkeypatch.setenv("AUTOGLM_TRACE_ENABLED", "1")

    with pytest.raises(RuntimeError, match="boom"):
        with trace_span("error-span", new_trace=True):
            raise RuntimeError("boom")

    records = _read_trace_records(trace_file)
    assert records[0]["name"] == "error-span"
    assert records[0]["status"] == "error"
    assert records[0]["error"] == {"message": "boom", "type": "RuntimeError"}
