"""Typed exception hierarchy (PRD 01 §7, PRD 04 §6).

Services and providers raise these; the API layer maps them to the uniform
error envelope. Bad external data fails fast and loud (assertive programming).
"""
from __future__ import annotations


class AtlasError(Exception):
    """Base for all application errors."""

    code = "INTERNAL"
    http_status = 500

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.message = message
        self.context = context


class ValidationError(AtlasError):
    code = "INVALID_REQUEST"
    http_status = 400


class NotFoundError(AtlasError):
    code = "NOT_FOUND"
    http_status = 404


class UnauthorizedError(AtlasError):
    code = "UNAUTHORIZED"
    http_status = 401


class RateLimitError(AtlasError):
    code = "RATE_LIMITED"
    http_status = 429


class ProviderError(AtlasError):
    code = "PROVIDER_UNAVAILABLE"
    http_status = 503
