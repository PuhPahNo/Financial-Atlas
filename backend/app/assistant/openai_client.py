"""Small Responses API client that cannot bypass the Atlas budget ledger."""
from __future__ import annotations

from typing import Any

import httpx

from ..core.config import settings
from ..core.errors import ProviderError
from . import budget


def create_response(payload: dict[str, Any], *, session_id: int | None = None) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise ProviderError("OpenAI is not configured for this Atlas environment.")
    reservation = budget.reserve(payload, session_id=session_id)
    try:
        with httpx.Client(timeout=settings.openai_timeout_seconds) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        budget.settle(reservation, data)
        return data
    except httpx.HTTPStatusError as exc:
        budget.release(reservation)
        status = exc.response.status_code
        raise ProviderError(f"OpenAI returned HTTP {status} for the research request.") from exc
    except httpx.HTTPError as exc:
        budget.release(reservation)
        raise ProviderError("OpenAI could not be reached for the research request.") from exc
    except Exception:
        budget.release(reservation)
        raise
