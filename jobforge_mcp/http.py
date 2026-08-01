from __future__ import annotations

import hmac
import os
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

from jobforge_mcp.server import mcp


ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[dict[str, Any]]], Callable[..., Awaitable[None]]], Awaitable[None]]


class BearerTokenMiddleware:
    """Fail-closed bearer authentication for the remote MCP transport."""

    def __init__(self, wrapped: ASGIApp) -> None:
        self.wrapped = wrapped

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.wrapped(scope, receive, send)
            return

        if scope.get("path") == "/health":
            configured = bool(os.getenv("JOBFORGE_MCP_API_TOKEN", "").strip())
            response = JSONResponse(
                {"status": "ready" if configured else "locked", "authentication_configured": configured}
            )
            await response(scope, receive, send)
            return

        expected = os.getenv("JOBFORGE_MCP_API_TOKEN", "").strip()
        supplied = _bearer_token(scope.get("headers", []))
        if not expected:
            response = JSONResponse({"error": "Remote MCP authentication is not configured."}, status_code=503)
            await response(scope, receive, send)
            return
        if not supplied or not hmac.compare_digest(supplied, expected):
            response = JSONResponse(
                {"error": "A valid bearer token is required."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.wrapped(scope, receive, send)


def _bearer_token(headers: list[tuple[bytes, bytes]]) -> str | None:
    for key, value in headers:
        if key.lower() != b"authorization":
            continue
        scheme, separator, token = value.decode("latin-1").partition(" ")
        if separator and scheme.lower() == "bearer" and token.strip():
            return token.strip()
    return None


app = BearerTokenMiddleware(mcp.streamable_http_app())
