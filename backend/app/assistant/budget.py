"""Durable reservation ledger for the application-level OpenAI hard cap.

Every paid request reserves a conservative worst-case amount before network I/O.
The reservation is reconciled against OpenAI's reported usage afterward. This
prevents two concurrent requests from both seeing the same remaining dollars.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from typing import Any

from ..core.config import settings
from ..core.errors import BudgetExhaustedError
from ..db import _now, session_scope
from ..models.assistant import OpenAIBudget, OpenAIUsage

_LOCK = threading.RLock()
_MICRO = Decimal("1000000")


def _usd_to_micro(value: float) -> int:
    return int((Decimal(str(value)) * _MICRO).to_integral_value(rounding=ROUND_CEILING))


def _token_cost_micro(*, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> int:
    cached = max(0, min(int(cached_input_tokens), int(input_tokens)))
    uncached = max(0, int(input_tokens) - cached)
    cost = (
        Decimal(uncached) * Decimal(str(settings.openai_input_usd_per_million))
        + Decimal(cached) * Decimal(str(settings.openai_cached_input_usd_per_million))
        + Decimal(max(0, int(output_tokens))) * Decimal(str(settings.openai_output_usd_per_million))
    )
    return int(cost.to_integral_value(rounding=ROUND_CEILING))


def estimate_reservation_micro(request_payload: dict[str, Any]) -> int:
    """Upper-bound input tokens by UTF-8 bytes and reserve all allowed output.

    BPE token counts cannot exceed the request's non-empty byte count for normal
    text/JSON. The extra 1 KiB covers HTTP/model framing that is not in the body.
    This intentionally over-reserves and is reconciled after the response.
    """
    encoded = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    input_upper_bound = len(encoded) + 1024
    output_upper_bound = int(request_payload.get("max_output_tokens") or settings.openai_max_output_tokens)
    return max(1, _token_cost_micro(
        input_tokens=input_upper_bound,
        cached_input_tokens=0,
        output_tokens=output_upper_bound,
    ))


def _budget_row(session) -> OpenAIBudget:
    row = session.query(OpenAIBudget).filter_by(id=1).with_for_update().one_or_none()
    if row is None:
        row = OpenAIBudget(
            id=1,
            spent_microusd=0,
            reserved_microusd=0,
            qa_spent_microusd=0,
            qa_reserved_microusd=0,
        )
        session.add(row)
        session.flush()
    return row


def _release_stale(session) -> None:
    cutoff = _now() - timedelta(minutes=10)
    stale = session.query(OpenAIUsage).filter(
        OpenAIUsage.status == "reserved",
        OpenAIUsage.created_at < cutoff,
    ).all()
    if not stale:
        return
    budget = _budget_row(session)
    for usage in stale:
        budget.reserved_microusd = max(0, budget.reserved_microusd - usage.reserved_microusd)
        if usage.purpose == "qa":
            budget.qa_reserved_microusd = max(0, budget.qa_reserved_microusd - usage.reserved_microusd)
        usage.status = "released"
        usage.settled_at = _now()


def reserve(request_payload: dict[str, Any], *, session_id: int | None = None, purpose: str | None = None) -> str:
    purpose = purpose or settings.openai_usage_mode
    if purpose not in {"production", "qa"}:
        raise ValueError("OpenAI usage purpose must be production or qa")
    amount = estimate_reservation_micro(request_payload)
    global_limit = _usd_to_micro(settings.openai_global_budget_usd)
    qa_limit = _usd_to_micro(settings.openai_qa_budget_usd)

    with _LOCK, session_scope() as session:
        _release_stale(session)
        budget = _budget_row(session)
        global_committed = budget.spent_microusd + budget.reserved_microusd
        if global_committed + amount > global_limit:
            raise BudgetExhaustedError(
                "Atlas AI has reached its $25 global OpenAI budget.",
                limit_usd=settings.openai_global_budget_usd,
                remaining_usd=max(0, global_limit - global_committed) / 1_000_000,
            )
        if purpose == "qa":
            qa_committed = budget.qa_spent_microusd + budget.qa_reserved_microusd
            if qa_committed + amount > qa_limit:
                raise BudgetExhaustedError(
                    "Atlas AI QA has reached its $10 OpenAI test budget.",
                    limit_usd=settings.openai_qa_budget_usd,
                    remaining_usd=max(0, qa_limit - qa_committed) / 1_000_000,
                )

        key = str(uuid.uuid4())
        session.add(OpenAIUsage(
            reservation_key=key,
            session_id=session_id,
            purpose=purpose,
            model=str(request_payload.get("model") or settings.openai_model),
            status="reserved",
            reserved_microusd=amount,
        ))
        budget.reserved_microusd += amount
        if purpose == "qa":
            budget.qa_reserved_microusd += amount
        budget.updated_at = _now()
        return key


def settle(reservation_key: str, response: dict[str, Any]) -> int:
    usage_data = response.get("usage") or {}
    details = usage_data.get("input_tokens_details") or {}
    input_tokens = int(usage_data.get("input_tokens") or 0)
    cached_tokens = int(details.get("cached_tokens") or 0)
    output_tokens = int(usage_data.get("output_tokens") or 0)
    actual = _token_cost_micro(
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
    )

    with _LOCK, session_scope() as session:
        ledger = session.query(OpenAIUsage).filter_by(reservation_key=reservation_key).with_for_update().one()
        if ledger.status != "reserved":
            return ledger.cost_microusd
        if actual > ledger.reserved_microusd:
            # The byte-based estimator should make this impossible. Failing loudly is
            # safer than silently pretending a hard budget is still trustworthy.
            raise RuntimeError("OpenAI usage exceeded its conservative budget reservation")
        budget = _budget_row(session)
        budget.reserved_microusd = max(0, budget.reserved_microusd - ledger.reserved_microusd)
        budget.spent_microusd += actual
        if ledger.purpose == "qa":
            budget.qa_reserved_microusd = max(0, budget.qa_reserved_microusd - ledger.reserved_microusd)
            budget.qa_spent_microusd += actual
        ledger.status = "settled"
        ledger.response_id = response.get("id")
        ledger.cost_microusd = actual
        ledger.input_tokens = input_tokens
        ledger.cached_input_tokens = cached_tokens
        ledger.output_tokens = output_tokens
        ledger.settled_at = _now()
        budget.updated_at = _now()
    return actual


def release(reservation_key: str) -> None:
    with _LOCK, session_scope() as session:
        ledger = session.query(OpenAIUsage).filter_by(reservation_key=reservation_key).with_for_update().one_or_none()
        if ledger is None or ledger.status != "reserved":
            return
        budget = _budget_row(session)
        budget.reserved_microusd = max(0, budget.reserved_microusd - ledger.reserved_microusd)
        if ledger.purpose == "qa":
            budget.qa_reserved_microusd = max(0, budget.qa_reserved_microusd - ledger.reserved_microusd)
        ledger.status = "released"
        ledger.settled_at = _now()
        budget.updated_at = _now()


def status() -> dict[str, Any]:
    with _LOCK, session_scope() as session:
        _release_stale(session)
        budget = _budget_row(session)
        global_limit = _usd_to_micro(settings.openai_global_budget_usd)
        qa_limit = _usd_to_micro(settings.openai_qa_budget_usd)
        committed = budget.spent_microusd + budget.reserved_microusd
        qa_committed = budget.qa_spent_microusd + budget.qa_reserved_microusd
        return {
            "model": settings.openai_model,
            "enabled": bool(settings.openai_api_key),
            "limit_usd": global_limit / 1_000_000,
            "spent_usd": budget.spent_microusd / 1_000_000,
            "reserved_usd": budget.reserved_microusd / 1_000_000,
            "remaining_usd": max(0, global_limit - committed) / 1_000_000,
            "qa_limit_usd": qa_limit / 1_000_000,
            "qa_spent_usd": budget.qa_spent_microusd / 1_000_000,
            "qa_reserved_usd": budget.qa_reserved_microusd / 1_000_000,
            "qa_remaining_usd": max(0, qa_limit - qa_committed) / 1_000_000,
        }
