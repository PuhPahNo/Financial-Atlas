"""Backtest integrity report (PRD backtest-integrity).

Every run returns an explicit, honest account of the bias controls that were (and
were not) in effect, so a good-looking equity curve can never quietly rest on
look-ahead or survivorship cheats. Statuses: ``pass`` (controlled), ``warn``
(residual risk the user should know about), ``info`` (not applicable to this run).
"""
from __future__ import annotations


def _check(check_id: str, label: str, status: str, detail: str) -> dict:
    return {"id": check_id, "label": label, "status": status, "detail": detail}


def build_integrity(
    *,
    mode: str,  # "buy_hold" | "rules" | "active_screen" | "fixture"
    uses_fundamentals: bool = False,
    membership_pit: bool | None = None,
    transaction_cost_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> dict:
    checks: list[dict] = []

    if mode == "fixture":
        checks.append(_check("fixture", "Fixture data", "info",
                             "Deterministic fixture bars used for contract testing — not market data."))
        return {"checks": checks, "grade": "info"}

    checks.append(_check(
        "adjusted_prices", "Split & dividend adjusted prices", "pass",
        "All fills and marks use dividend/split-adjusted closes, so splits don't fake "
        "crashes and dividend income isn't dropped from returns."))

    if mode == "buy_hold":
        checks.append(_check(
            "execution", "Execution timing", "pass",
            "Single buy at the first close of the window and a mark-to-market hold — no "
            "signal exists to leak."))
    else:
        checks.append(_check(
            "execution", "Next-bar execution", "pass",
            "Signals computed on day D fill at the next session's close — the engine "
            "never trades on the same bar that produced the signal."))

    if uses_fundamentals:
        checks.append(_check(
            "fundamentals", "Point-in-time fundamentals", "pass",
            "Only originally-filed SEC figures visible on or before each historical date "
            "are used (original filing dates, not restated comparatives)."))
    else:
        checks.append(_check(
            "fundamentals", "Point-in-time fundamentals", "info",
            "This strategy trades on price signals only; no fundamental data is used."))

    if mode == "active_screen":
        if membership_pit is True:
            checks.append(_check(
                "membership", "Historical index membership", "pass",
                "The S&P 500 universe is reconstructed as it stood on each trading day "
                "from the published add/remove change-log."))
        elif membership_pit is None:
            checks.append(_check(
                "membership", "Universe selection", "info",
                "The model trades a fixed basket it defines (e.g. an ETF rotation set) — "
                "index membership does not apply."))
        else:
            checks.append(_check(
                "membership", "Historical index membership", "warn",
                "The universe is today's list (or user-specified) — names that left the "
                "index are missing, which can flatter results."))
        if membership_pit is not None:
            checks.append(_check(
                "delistings", "Delisted-ticker coverage", "warn",
                "Free price providers lack history for some delisted names; those are "
                "skipped, so a residual survivorship tilt can remain."))

    cost = transaction_cost_bps + slippage_bps
    checks.append(_check(
        "costs", "Transaction costs & slippage", "pass" if cost > 0 else "warn",
        f"Each fill is charged {cost:g} bps (commission + slippage)." if cost > 0 else
        "No transaction costs were modeled — real-world results would be lower."))

    checks.append(_check(
        "eod_data", "End-of-day data", "warn",
        "Daily closes only: intraday stop/take-profit levels are evaluated at the close, "
        "so fast intraday moves are approximated."))

    grade = "warn" if any(c["status"] == "warn" for c in checks) else "pass"
    return {"checks": checks, "grade": grade}
