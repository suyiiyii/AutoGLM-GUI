"""Guards for high-privilege local control endpoints."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request


_TRUSTED_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def require_local_control_access(request: Request) -> None:
    """Only allow loopback access unless explicitly disabled for debugging."""
    if os.getenv("AUTOGLM_UNSAFE_ALLOW_REMOTE_CONTROL", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        return

    client_host = request.client.host if request.client else None
    if client_host in _TRUSTED_LOOPBACK_HOSTS:
        return

    raise HTTPException(
        status_code=403,
        detail=(
            "Local control plane is restricted to loopback requests. "
            "Set AUTOGLM_UNSAFE_ALLOW_REMOTE_CONTROL=1 only for explicit debugging."
        ),
    )
