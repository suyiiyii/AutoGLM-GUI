"""Structured model error details for UI and trace diagnostics."""

from __future__ import annotations

import traceback
from collections.abc import Mapping
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError

from AutoGLM_GUI.config import ModelConfig
from AutoGLM_GUI.trace import summarize_text

_REDACTED_HEADER_NAMES = {
    "authorization",
    "api-key",
    "x-api-key",
    "x-goog-api-key",
    "cookie",
    "set-cookie",
}
_MAX_BODY_CHARS = 20000


def _redact_header_value(name: str, value: str) -> str:
    if name.lower() in _REDACTED_HEADER_NAMES:
        return "[REDACTED]"
    return value


def _headers_to_dict(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, Mapping):
        items = headers.items()
    else:
        try:
            items = headers.items()
        except AttributeError:
            return {}
    return {
        str(key): _redact_header_value(str(key), str(value)) for key, value in items
    }


def _response_body_text(exc: APIStatusError) -> str | None:
    body = getattr(exc, "body", None)
    if body is not None:
        return summarize_text(str(body), limit=_MAX_BODY_CHARS)

    response = getattr(exc, "response", None)
    if response is None:
        return None
    text = getattr(response, "text", None)
    if text is None:
        return None
    return summarize_text(str(text), limit=_MAX_BODY_CHARS)


def serialize_model_error(
    exc: BaseException,
    *,
    model_config: ModelConfig,
    call_site: str,
    include_traceback: bool = False,
) -> dict[str, Any]:
    """Return UI/trace-safe structured details for model call failures."""
    details: dict[str, Any] = {
        "kind": "model_error",
        "exception_type": exc.__class__.__name__,
        "message": str(exc),
        "model_name": model_config.model_name,
        "base_url": model_config.base_url,
        "call_site": call_site,
    }

    if isinstance(exc, APIStatusError):
        response = getattr(exc, "response", None)
        request_id = getattr(exc, "request_id", None)
        if request_id is None and response is not None:
            request_id = getattr(response, "headers", {}).get("x-request-id")
        details.update(
            {
                "kind": "model_http_error",
                "status_code": getattr(response, "status_code", None),
                "request_id": request_id,
                "response_headers": _headers_to_dict(
                    getattr(response, "headers", None)
                ),
                "response_body": _response_body_text(exc),
            }
        )
    elif isinstance(exc, APITimeoutError):
        details["kind"] = "model_timeout"
    elif isinstance(exc, APIConnectionError):
        details["kind"] = "model_connection_error"

    if include_traceback:
        details["traceback"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

    return {key: value for key, value in details.items() if value is not None}


def model_error_message(exc: BaseException) -> str:
    """Return the short message shown in existing compact task surfaces."""
    return f"Model error: {exc}"


def trace_error_attrs(details: dict[str, Any]) -> dict[str, Any]:
    """Convert structured details into namespaced span attributes."""
    attrs: dict[str, Any] = {
        "error_kind": details.get("kind"),
        "error_type": details.get("exception_type"),
        "error_message": details.get("message"),
        "model_name": details.get("model_name"),
        "base_url": details.get("base_url"),
        "call_site": details.get("call_site"),
    }
    if "status_code" in details:
        attrs["http.status_code"] = details["status_code"]
    if "request_id" in details:
        attrs["http.request_id"] = details["request_id"]
    if "response_headers" in details:
        attrs["http.response_headers"] = details["response_headers"]
    if "response_body" in details:
        attrs["http.response_body"] = details["response_body"]
    return {key: value for key, value in attrs.items() if value is not None}
