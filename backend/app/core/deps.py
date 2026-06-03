"""FastAPI dependencies for protected Atlas workflows."""
from __future__ import annotations

from fastapi import Request

from .auth import require_auth
from .rate_limit import rate_limit_assistant, rate_limit_paper_trading


def require_paper_trading_access(request: Request) -> dict:
    user = require_auth(request)
    rate_limit_paper_trading(request)
    return user


def require_assistant_access(request: Request) -> dict:
    user = require_auth(request)
    rate_limit_assistant(request)
    return user


def require_edit_access(request: Request) -> dict:
    user = require_auth(request)
    rate_limit_paper_trading(request)
    return user
