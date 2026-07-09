"""Small signed-cookie auth layer for protected Atlas workflows."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Request

from .config import settings
from .errors import UnauthorizedError


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(payload: str) -> str:
    return _b64url(hmac.new(settings.auth_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())


def create_session_token(username: str, *, ttl_seconds: int | None = None) -> str:
    now = int(time.time())
    ttl = ttl_seconds if ttl_seconds is not None else settings.auth_session_ttl_seconds
    payload = _b64url(json.dumps({"sub": username, "iat": now, "exp": now + ttl}, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(payload)}"


def verify_session_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        claims = json.loads(_b64url_decode(payload))
    except (ValueError, TypeError):
        return None
    if int(claims.get("exp") or 0) < int(time.time()):
        return None
    if claims.get("sub") != settings.auth_username:
        return None
    return claims


def require_auth(request: Request) -> dict[str, Any]:
    if not settings.auth_required:
        return {"sub": settings.auth_username, "auth_disabled": True}
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    claims = verify_session_token(token)
    if not claims:
        raise UnauthorizedError("Login required")
    return claims
