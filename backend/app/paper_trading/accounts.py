"""Trader accounts — simulated 'fake trader' profiles that allocate capital
across several strategies. Performance is a capital-weighted blend of each
allocated strategy's backtest over a shared window."""
from __future__ import annotations

import bisect
from datetime import date, datetime, timezone

from ..backtesting.engine import run_backtest as execute_backtest
from ..backtesting.metrics import max_drawdown
from ..core import cache, market_hours
from ..core.errors import NotFoundError, ValidationError
from ..core.matching import best_name_match
from ..db import session_scope
from ..models.paper_trading import AccountAllocation, TraderAccount, TradingStrategy
from ..services import prices
from .schemas import AccountCreate, AccountRebalanceRequest, AccountUpdate, normalize_tickers
from .service import _strategy_view


def _account_view(account: TraderAccount, strategies: dict[int, TradingStrategy]) -> dict:
    allocs = []
    for a in account.allocations:
        st = strategies.get(a.strategy_id)
        allocs.append({
            "strategy_id": a.strategy_id,
            "weight": a.weight,
            "name": st.name if st else f"Strategy {a.strategy_id}",
            "category": st.category if st else None,
            "strategy_status": st.status if st else "missing",
            "archived": bool(st and st.status != "active"),
            "dollars": round(account.starting_cash * a.weight / 100, 2),
        })
    invested = sum(a["weight"] for a in allocs)
    cash = round(max(0.0, 100 - invested), 2)
    return {
        "id": account.id,
        "name": account.name,
        "emoji": account.emoji or "🦈",
        "bio": account.bio or "",
        "starting_cash": account.starting_cash,
        "status": account.status,
        "allocations": allocs,
        "invested_pct": round(invested, 2),
        "cash_pct": cash,
        "reconciled_pct": round(invested + cash, 2),
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def _strategies_map(session, account: TraderAccount) -> dict[int, TradingStrategy]:
    ids = [a.strategy_id for a in account.allocations]
    if not ids:
        return {}
    rows = session.query(TradingStrategy).filter(TradingStrategy.id.in_(ids)).all()
    return {row.id: row for row in rows}


def _validate_allocations(session, allocations, *, allow_inactive_ids: set[int] | None = None) -> None:
    allow_inactive_ids = allow_inactive_ids or set()
    total = 0.0
    seen: set[int] = set()
    for a in allocations:
        if a.strategy_id in seen:
            raise ValidationError(f"Strategy {a.strategy_id} is allocated more than once")
        seen.add(a.strategy_id)
        total += a.weight
        strat = session.get(TradingStrategy, a.strategy_id)
        if not strat or (strat.status != "active" and a.strategy_id not in allow_inactive_ids):
            raise ValidationError(f"Strategy {a.strategy_id} not found or inactive")
    if total > 100.0001:
        raise ValidationError(f"Allocations sum to {total:.0f}% — they cannot exceed 100% of capital")


def _active_account(session, account_id: int) -> TraderAccount:
    account = session.get(TraderAccount, account_id)
    if not account or account.status != "active":
        raise NotFoundError(f"Trader account {account_id} not found")
    return account


def _replace_allocations(session, account: TraderAccount, allocations) -> None:
    for existing in list(account.allocations):
        session.delete(existing)
    session.flush()
    for allocation in allocations:
        if allocation.weight > 0:
            session.add(AccountAllocation(
                account_id=account.id,
                strategy_id=allocation.strategy_id,
                weight=allocation.weight,
            ))
    session.flush()
    session.expire(account, ["allocations"])


def _rebalance_context(session, account_id: int, allocations):
    account = _active_account(session, account_id)
    existing_ids = {allocation.strategy_id for allocation in account.allocations}
    _validate_allocations(session, allocations, allow_inactive_ids=existing_ids)
    strategy_ids = existing_ids | {allocation.strategy_id for allocation in allocations}
    strategies = (
        {strategy.id: strategy for strategy in session.query(TradingStrategy).filter(
            TradingStrategy.id.in_(strategy_ids)
        ).all()}
        if strategy_ids else {}
    )
    return account, strategies


def _rebalance_preview(account: TraderAccount, allocations, strategies: dict[int, TradingStrategy]) -> dict:
    current = {a.strategy_id: float(a.weight) for a in account.allocations}
    target = {a.strategy_id: float(a.weight) for a in allocations if a.weight > 0}
    ids = sorted(set(current) | set(target))
    orders = []
    for sid in ids:
        st = strategies.get(sid)
        current_weight = current.get(sid, 0.0)
        target_weight = target.get(sid, 0.0)
        delta = target_weight - current_weight
        current_dollars = account.starting_cash * current_weight / 100
        target_dollars = account.starting_cash * target_weight / 100
        action = "hold"
        if delta > 0:
            action = "buy"
        elif delta < 0:
            action = "sell"
        orders.append({
            "strategy_id": sid,
            "name": st.name if st else f"Strategy {sid}",
            "category": st.category if st else None,
            "strategy_status": st.status if st else "missing",
            "archived": bool(st and st.status != "active"),
            "current_weight": round(current_weight, 2),
            "target_weight": round(target_weight, 2),
            "delta_weight": round(delta, 2),
            "current_dollars": round(current_dollars, 2),
            "target_dollars": round(target_dollars, 2),
            "trade_dollars": round(target_dollars - current_dollars, 2),
            "action": action,
        })
    current_invested = sum(current.values())
    target_invested = sum(target.values())
    return {
        "account_id": account.id,
        "starting_cash": account.starting_cash,
        "current_invested_pct": round(current_invested, 2),
        "target_invested_pct": round(target_invested, 2),
        "current_cash_pct": round(max(0.0, 100 - current_invested), 2),
        "target_cash_pct": round(max(0.0, 100 - target_invested), 2),
        "current_reconciled_pct": round(current_invested + max(0.0, 100 - current_invested), 2),
        "target_reconciled_pct": round(target_invested + max(0.0, 100 - target_invested), 2),
        "orders": orders,
    }


def create_account(payload: AccountCreate) -> dict:
    with session_scope() as session:
        _validate_allocations(session, payload.allocations)
        account = TraderAccount(
            name=payload.name.strip(), emoji=payload.emoji or "🦈", bio=payload.bio or "",
            starting_cash=payload.starting_cash,
        )
        session.add(account)
        session.flush()
        _replace_allocations(session, account, payload.allocations)
        session.flush()
        return {"account": _account_view(account, _strategies_map(session, account))}


def list_accounts() -> dict:
    with session_scope() as session:
        accounts = session.query(TraderAccount).filter_by(status="active").order_by(TraderAccount.created_at.asc()).all()
        all_ids = {a.strategy_id for acc in accounts for a in acc.allocations}
        strategies = {}
        if all_ids:
            strategies = {s.id: s for s in session.query(TradingStrategy).filter(TradingStrategy.id.in_(all_ids)).all()}
        return {"accounts": [_account_view(acc, strategies) for acc in accounts]}


def get_account(account_id: int) -> dict:
    with session_scope() as session:
        account = _active_account(session, account_id)
        return {"account": _account_view(account, _strategies_map(session, account))}


def update_account(account_id: int, payload: AccountUpdate) -> dict:
    data = payload.model_dump(exclude_unset=True)
    with session_scope() as session:
        account = _active_account(session, account_id)
        if "name" in data and data["name"]:
            account.name = data["name"].strip()
        for field in ("emoji", "bio", "starting_cash"):
            if field in data and data[field] is not None:
                setattr(account, field, data[field])
        if "allocations" in data and data["allocations"] is not None:
            existing_ids = {a.strategy_id for a in account.allocations}
            _validate_allocations(session, payload.allocations, allow_inactive_ids=existing_ids)
            _replace_allocations(session, account, payload.allocations)
        session.flush()
        session.refresh(account)
        return {"account": _account_view(account, _strategies_map(session, account))}


def rebalance_preview(account_id: int, payload: AccountRebalanceRequest) -> dict:
    with session_scope() as session:
        account, strategies = _rebalance_context(session, account_id, payload.allocations)
        return {"preview": _rebalance_preview(account, payload.allocations, strategies)}


def rebalance_account(account_id: int, payload: AccountRebalanceRequest) -> dict:
    with session_scope() as session:
        account, strategies = _rebalance_context(session, account_id, payload.allocations)
        preview = _rebalance_preview(account, payload.allocations, strategies)
        _replace_allocations(session, account, payload.allocations)
        session.flush()
        session.refresh(account)
        return {"account": _account_view(account, _strategies_map(session, account)), "preview": preview}


def delete_account(account_id: int) -> dict:
    with session_scope() as session:
        account = _active_account(session, account_id)
        account.status = "archived"
    return {"deleted": account_id}


def assign_strategy_to_account(*, account_name: str, strategy_name: str, weight: float) -> dict:
    """Set one strategy allocation on an active simulated trader account."""
    if weight <= 0 or weight > 100:
        raise ValidationError("Allocation weight must be between 0 and 100")
    with session_scope() as session:
        accounts = session.query(TraderAccount).filter_by(status="active").all()
        account = best_name_match(accounts, account_name)
        if account is None:
            raise NotFoundError(f"Trader account '{account_name}' not found")

        strategies = session.query(TradingStrategy).filter_by(status="active").all()
        strategy = best_name_match(strategies, strategy_name)
        if strategy is None:
            raise NotFoundError(f"Strategy '{strategy_name}' not found")

        existing = (
            session.query(AccountAllocation)
            .filter_by(account_id=account.id, strategy_id=strategy.id)
            .first()
        )
        other_total = sum(a.weight for a in account.allocations if existing is None or a.id != existing.id)
        if other_total + weight > 100.0001:
            raise ValidationError(
                f"Allocations would sum to {other_total + weight:.0f}% — they cannot exceed 100% of capital"
            )
        if existing:
            existing.weight = weight
        else:
            session.add(AccountAllocation(account_id=account.id, strategy_id=strategy.id, weight=weight))
        session.flush()
        session.refresh(account)
        view = _account_view(account, _strategies_map(session, account))
        return {
            "account": view,
            "assigned": {
                "strategy_id": strategy.id,
                "strategy_name": strategy.name,
                "account_id": account.id,
                "account_name": account.name,
                "weight": weight,
            },
        }


def _default_window() -> tuple[date, date]:
    today = date.today()
    return date(today.year - 3, today.month, 1), today


def _downsample(points: list[dict], n: int = 120) -> list[dict]:
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    return [points[min(round(i * step), len(points) - 1)] for i in range(n)]


def _drawdown_curve(points: list[dict]) -> list[dict]:
    peak = None
    out = []
    for point in points:
        equity = float(point["equity"])
        peak = equity if peak is None else max(peak, equity)
        dd = (equity - peak) / peak if peak else 0.0
        out.append({"date": point["date"], "drawdown": round(dd, 4)})
    return out


def _account_sleeves(account_id: int) -> tuple[float, list[tuple[int, float, dict]]]:
    with session_scope() as session:
        account = _active_account(session, account_id)
        strategies = _strategies_map(session, account)
        starting_cash = float(account.starting_cash)
        sleeves = [
            (allocation.strategy_id, float(allocation.weight), _strategy_view(strategies[allocation.strategy_id]))
            for allocation in account.allocations
            if allocation.strategy_id in strategies and allocation.weight > 0
        ]
    return starting_cash, sleeves


def _execute_sleeve(view: dict, dollars: float, start: date, end: date) -> dict:
    return execute_backtest(
        strategy=view,
        tickers=normalize_tickers(view.get("parameters", {}).get("tickers", [])),
        start_date=start,
        end_date=end,
        starting_cash=dollars,
        benchmark="SPY",
    )


def account_performance(account_id: int, start: date | None = None, end: date | None = None) -> dict:
    if start is None or end is None:
        start, end = _default_window()
    starting_cash, allocs = _account_sleeves(account_id)

    invested_dollars = sum(starting_cash * w / 100 for _, w, _ in allocs)
    cash_dollars = max(0.0, starting_cash - invested_dollars)

    per: list[dict] = []
    warnings: list[str] = []
    all_dates: set[str] = set()
    for sid, weight, view in allocs:
        dollars = starting_cash * weight / 100
        try:
            res = _execute_sleeve(view, dollars, start, end)
        except Exception as exc:  # noqa: BLE001 — a single broken sleeve shouldn't kill the account
            warnings.append(f"{view['name']}: {exc}")
            continue
        curve = res.get("equity_curve") or []
        dates = [str(p["date"]) for p in curve]
        all_dates.update(dates)
        eq = {str(p["date"]): float(p["equity"]) for p in curve}
        bm = {str(p["date"]): float(p["benchmark_equity"]) for p in curve if p.get("benchmark_equity") is not None}
        final = curve[-1]["equity"] if curve else dollars
        turnover = sum(abs(float(t.get("value") or 0)) for t in res.get("trades", [])) / dollars if dollars else 0.0
        per.append({
            "strategy_id": sid, "name": view["name"], "category": view["category"],
            "strategy_status": view.get("status", "active"), "archived": view.get("status") != "active",
            "weight": weight, "dollars": round(dollars, 2),
            "final": round(final, 2), "pnl": round(final - dollars, 2),
            "return_pct": round((final / dollars - 1) * 100, 2) if dollars else 0.0,
            "turnover": round(turnover, 4),
            "eq": eq, "bm": bm, "dates": sorted(dates),
        })
        warnings.extend(res.get("warnings", [])[:1])

    ordered = sorted(all_dates)

    def cf(value_map: dict, dates_sorted: list[str], target: str, default: float) -> float:
        i = bisect.bisect_right(dates_sorted, target) - 1
        return value_map.get(dates_sorted[i], default) if i >= 0 else default

    blended: list[dict] = []
    for d in ordered:
        eq_sum = cash_dollars
        bm_sum = cash_dollars
        for p in per:
            eq_sum += cf(p["eq"], p["dates"], d, p["dollars"])
            bm_sum += cf(p["bm"], p["dates"], d, p["dollars"])
        blended.append({"date": d, "equity": round(eq_sum, 2), "benchmark_equity": round(bm_sum, 2)})

    if blended:
        current = blended[-1]["equity"]
        bench_final = blended[-1]["benchmark_equity"]
    else:
        current = starting_cash
        bench_final = starting_cash
    total_return = current / starting_cash - 1
    bench_return = bench_final / starting_cash - 1
    dd = max_drawdown([{"equity": b["equity"]} for b in blended]) if blended else 0.0

    contributions = sorted(
        [{k: p[k] for k in ("strategy_id", "name", "category", "strategy_status", "archived", "weight", "dollars", "final", "pnl", "return_pct", "turnover")} for p in per],
        key=lambda c: c["pnl"], reverse=True,
    )
    contribution_final = round(sum(c["final"] for c in contributions), 2)
    weights = [c["weight"] / 100 for c in contributions]
    risk = {
        "gross_exposure": round(invested_dollars / starting_cash, 4) if starting_cash else 0.0,
        "cash_pct": round(cash_dollars / starting_cash, 4) if starting_cash else 0.0,
        "concentration": round(max(weights), 4) if weights else 0.0,
        "herfindahl": round(sum(w * w for w in weights), 4),
        "turnover": round(sum(c["turnover"] * c["dollars"] for c in contributions) / starting_cash, 4) if starting_cash else 0.0,
        "max_drawdown": round(dd, 4),
    }
    attribution = {
        "top_contributors": contributions[:3],
        "laggards": sorted(contributions, key=lambda c: c["pnl"])[:3],
        "allocation": [
            {
                "strategy_id": c["strategy_id"],
                "name": c["name"],
                "category": c["category"],
                "weight": c["weight"],
                "dollars": c["dollars"],
                "archived": c.get("archived", False),
            }
            for c in contributions
        ],
        "reconciliation": {
            "contribution_final": contribution_final,
            "cash_dollars": round(cash_dollars, 2),
            "current_value": round(current, 2),
            "difference": round(current - contribution_final - cash_dollars, 2),
        },
    }

    return {
        "account_id": account_id,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        # This "history" is a re-simulation of the CURRENT allocation over the window,
        # not a realized trade record — it changes if the strategies or weights change.
        # The frontend surfaces this so the equity curve isn't mistaken for a live track record.
        "basis": "resimulated",
        "basis_note": ("Simulated: the current allocation replayed over this window on real prices. "
                       "Editing a strategy or its weights re-computes this curve — it is not a realized "
                       "trade record."),
        "starting_cash": starting_cash,
        "cash_dollars": round(cash_dollars, 2),
        "current_value": round(current, 2),
        "total_return": round(total_return, 4),
        "benchmark_return": round(bench_return, 4),
        "alpha": round(total_return - bench_return, 4),
        "max_drawdown": round(dd, 4),
        "equity": _downsample(blended),
        "drawdown_curve": _downsample(_drawdown_curve(blended)),
        "risk": risk,
        "attribution": attribution,
        "contributions": contributions,
        "warnings": list(dict.fromkeys(warnings))[:4],
    }


# --------------------------------------------------------------------------- #
# Live-ish valuation (PRD live-paper-valuation)                               #
#                                                                             #
# Splits the slow-moving *state* (the shares each strategy holds going into   #
# the next session) from the fast-moving *valuation* (marking those shares to #
# a ~15-min-delayed Yahoo quote). The settled-holdings snapshot is cached for #
# a trading day; the mark is recomputed on demand whenever a quote is fresher #
# than the cache. Both the read path and the in-process tick call             #
# ``ensure_fresh_mark`` so there is one freshness-gated code path.            #
# --------------------------------------------------------------------------- #

DELAYED_MINUTES = 15  # Yahoo free quotes are ~15-minute delayed.


def _holdings_window() -> tuple[date, date]:
    """Backtest window for settled holdings — ends on the last completed trading day so the
    settled position reflects a real session close, not an in-progress bar."""
    end = market_hours.last_trading_day()
    return date(end.year - 3, end.month, 1), end


def _leg_value(holding: dict, price: float) -> float:
    """Mark-to-market contribution of one settled position at ``price``.
    Long = qty·price; short = qty·(entry − price) added to cash."""
    qty = float(holding.get("quantity") or 0.0)
    if holding.get("direction") == "short":
        return qty * (float(holding.get("entry_price") or 0.0) - price)
    return qty * price


def _active_account_ids() -> list[int]:
    with session_scope() as session:
        rows = session.query(TraderAccount.id).filter_by(status="active").all()
        return [r[0] for r in rows]


def _compute_holdings(account_id: int) -> dict:
    """Run each allocated sleeve's backtest once and aggregate the settled positions the
    account holds going into the next session, plus the baseline cash and EOD value."""
    start, end = _holdings_window()
    starting_cash, allocs = _account_sleeves(account_id)

    invested_dollars = sum(starting_cash * weight / 100 for _, weight, _ in allocs)
    cash = max(0.0, starting_cash - invested_dollars)  # account-level uninvested cash
    holdings: list[dict] = []
    warnings: list[str] = []
    for _strategy_id, weight, view in allocs:
        dollars = starting_cash * weight / 100
        try:
            res = _execute_sleeve(view, dollars, start, end)
        except Exception as exc:  # noqa: BLE001 — one broken sleeve shouldn't sink the mark
            warnings.append(f"{view['name']}: {exc}")
            cash += dollars  # treat the unresolved sleeve as cash so totals still reconcile
            continue
        cash += float(res.get("residual_cash") or 0.0)
        for h in res.get("final_holdings", []) or []:
            if (h.get("quantity") or 0) and h.get("last_close") is not None:
                holdings.append({
                    "ticker": str(h["ticker"]).upper(),
                    "quantity": float(h["quantity"]),
                    "direction": h.get("direction", "long"),
                    "entry_price": float(h.get("entry_price") or 0.0),
                    "last_close": float(h["last_close"]),
                })

    eod_value = cash + sum(_leg_value(h, h["last_close"]) for h in holdings)
    return {
        "holdings": holdings,
        "cash": round(cash, 4),
        "tickers": sorted({h["ticker"] for h in holdings}),
        "eod_value": round(eod_value, 2),
        "as_of_date": end.isoformat(),
        "starting_cash": starting_cash,
        "warnings": list(dict.fromkeys(warnings))[:4],
    }


def account_holdings(account_id: int) -> dict:
    """Settled-holdings snapshot, cached for the trading day. The cache key folds in the
    last trading day, the allocation set, and starting cash, so the expensive backtests
    re-run at most ~once per trading day or whenever allocations change."""
    with session_scope() as session:
        account = _active_account(session, account_id)
        sig = ";".join(
            f"{a.strategy_id}:{a.weight}" for a in sorted(account.allocations, key=lambda x: x.strategy_id)
        )
        sig = f"{float(account.starting_cash)}|{sig}"
    key = f"{account_id}:{market_hours.last_trading_day().isoformat()}:{sig}"
    return cache.get_or_set(
        "account_holdings", key, ttl_seconds=24 * 3600, loader=lambda: _compute_holdings(account_id)
    ).value


def ensure_fresh_mark(account_id: int) -> dict:
    """Freshness-gated live mark. Loads the settled-holdings snapshot, then — only while the
    market is open — marks the held shares to a fresh quote and reports the day's change.
    Market closed, all-cash, or a failed quote fetch all fall back to the EOD baseline."""
    snap = account_holdings(account_id)
    cash = float(snap["cash"])
    holdings = snap["holdings"]
    eod_value = float(snap["eod_value"])
    now = datetime.now(timezone.utc)
    open_now = market_hours.is_market_open(now)

    result = {
        "account_id": account_id,
        "current_value": round(eod_value, 2),
        "eod_value": round(eod_value, 2),
        "day_change": 0.0,
        "day_change_pct": 0.0,
        "as_of": snap["as_of_date"],
        "market_open": open_now,
        "delayed_minutes": DELAYED_MINUTES,
        "served_by": "eod",
        "stale": False,
        "warnings": snap.get("warnings", []),
    }
    if not open_now or not holdings:
        return result

    quotes, served_by = prices.live_quotes(snap["tickers"])
    prev_value = cash
    live_value = cash
    marked = False
    for h in holdings:
        q = quotes.get(h["ticker"])
        price = getattr(q, "price", None) if q is not None else None
        if price is None:  # missing leg → no intraday move for it
            prev_value += _leg_value(h, h["last_close"])
            live_value += _leg_value(h, h["last_close"])
            continue
        marked = True
        prev = getattr(q, "previous_close", None)
        prev = float(prev) if prev is not None else h["last_close"]
        prev_value += _leg_value(h, prev)
        live_value += _leg_value(h, float(price))

    if not marked:  # every quote failed → serve the EOD baseline, flagged stale
        result["stale"] = True
        return result

    day_change = live_value - prev_value
    result["current_value"] = round(live_value, 2)
    result["day_change"] = round(day_change, 2)
    result["day_change_pct"] = round(day_change / prev_value, 4) if prev_value else 0.0
    result["as_of"] = now.isoformat()
    result["served_by"] = served_by
    return result


def warm_active_marks() -> int:
    """Pre-warm live marks for all active accounts (used by the in-process tick). Returns
    the number of accounts refreshed. Best-effort: a single failure never aborts the batch."""
    ids = _active_account_ids()
    refreshed = 0
    for account_id in ids:
        try:
            ensure_fresh_mark(account_id)
            refreshed += 1
        except Exception:  # noqa: BLE001 — keep the tick alive across a bad account
            continue
    return refreshed
