"""Export AutoGLM trace spans to OTLP-compatible JSONL."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

_OTLP_STATUS_CODE_OK = 1
_OTLP_STATUS_CODE_ERROR = 2


def _unix_nano(timestamp: Any) -> str | None:
    if not isinstance(timestamp, str) or not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return str(int(parsed.timestamp() * 1_000_000_000))


def _otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"intValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    if value is None:
        return {"stringValue": ""}
    if isinstance(value, str):
        return {"stringValue": value}
    return {"stringValue": json.dumps(value, ensure_ascii=False, default=str)}


def _attributes(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": str(key), "value": _otlp_value(value)} for key, value in attrs.items()
    ]


def _semantic_attrs(record: dict[str, Any]) -> dict[str, Any]:
    name = str(record.get("name", ""))
    attrs = dict(record.get("attrs") or {})
    if name == "step.llm":
        attrs.setdefault("openinference.span.kind", "LLM")
        attrs.setdefault("gen_ai.operation.name", "chat")
        model_name = attrs.get("model_name")
        if model_name is not None:
            attrs.setdefault("gen_ai.request.model", model_name)
    elif name in {"tool.call", "tool.result", "action.execute"}:
        attrs.setdefault("openinference.span.kind", "TOOL")
    elif name in {"agent.step", "agent.stream", "layered.planner.stream"}:
        attrs.setdefault("openinference.span.kind", "AGENT")
    return attrs


def span_to_otlp_json(record: dict[str, Any]) -> dict[str, Any]:
    """Convert one AutoGLM span JSON record into one OTLP JSON value."""
    span: dict[str, Any] = {
        "traceId": str(record.get("trace_id", "")),
        "spanId": str(record.get("span_id", "")),
        "name": str(record.get("name", "")),
        "attributes": _attributes(_semantic_attrs(record)),
        "status": {
            "code": _OTLP_STATUS_CODE_ERROR
            if record.get("status") == "error"
            else _OTLP_STATUS_CODE_OK
        },
    }
    parent_span_id = record.get("parent_span_id")
    if parent_span_id:
        span["parentSpanId"] = str(parent_span_id)

    start_time_unix_nano = _unix_nano(record.get("start_time"))
    end_time_unix_nano = _unix_nano(record.get("end_time"))
    if start_time_unix_nano is not None:
        span["startTimeUnixNano"] = start_time_unix_nano
    if end_time_unix_nano is not None:
        span["endTimeUnixNano"] = end_time_unix_nano

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": _attributes(
                        {
                            "service.name": "autoglm-gui",
                            "telemetry.sdk.name": "autoglm-trace-export",
                        }
                    )
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "AutoGLM_GUI.trace"},
                        "spans": [span],
                    }
                ],
            }
        ]
    }


def iter_otlp_jsonl(
    trace_file: Path,
    *,
    trace_id: str | None = None,
) -> Iterable[dict[str, Any]]:
    """Yield OTLP JSON values converted from an AutoGLM span JSONL file."""
    with trace_file.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            record = json.loads(line)
            if trace_id is not None and record.get("trace_id") != trace_id:
                continue
            if record.get("record_type", "span") != "span":
                continue
            yield span_to_otlp_json(record)


def export_otlp_jsonl(
    trace_file: Path,
    output_file: Path,
    *,
    trace_id: str | None = None,
) -> int:
    """Export AutoGLM span JSONL records into an OTLP JSONL file."""
    count = 0
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as output:
        for item in iter_otlp_jsonl(trace_file, trace_id=trace_id):
            output.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
            output.write("\n")
            count += 1
    return count
