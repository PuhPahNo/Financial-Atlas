"""Trader accounts — simulated 'fake trader' profiles that allocate capital
across several strategies. Performance is a capital-weighted blend of each
allocated strategy's backtest over a shared window."""
from __future__ import annotations

import bisect
from datetime import date, timedelta

from ..backtesting.engine import run_backtest as execute_backtest
from ..backtesting.metrics import max_drawdown
from ..core.errors import NotFoundError, ValidationError
from ..db import session_scope
from ..models.paper_trading import AccountAllocation, TraderAccount, TradingStrategy
from .schemas import AccountCreate, AccountUpdate, normalize_tickers
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
            "dollars": round(account.starting_cash * a.weight / 100, 2),
        })
    invested = sum(a["weight"] for a in allocs)
    return {
        "id": account.id,
        "name": account.name,
        "emoji": account.emoji or "🦈",
        "bio": account.bio or "",
        "starting_cash": account.starting_cash,
        "status": account.status,
        "allocations": allocs,
        "invested_pct": round(invested, 2),
        "cash_pct": round(max(0.0, 100 - invested), 2),
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def _strategies_map(session, account: TraderAccount) -> dict[int, TradingStrategy]:
    ids = [a.strategy_id for a in account.allocations]
    if not ids:
        return {}
    rows = session.query(TradingStrategy).filter(TradingStrategy.id.in_(ids)).all()
    return {row.id: row for row in rows}


def _validate_allocations(session, allocations) -> None:
    total = 0.0
    for a in allocations:
        total += a.weight
        strat = session.get(TradingStrategy, a.strategy_id)
        if not strat or strat.status != "active":
            raise ValidationError(f"Strategy {a.strategy_id} not found or inactive")
    if total > 100.0001:
        raise ValidationError(f"Allocations sum to {total:.0f}% — they cannot exceed 100% of capital")


def _tokens(value: str) -> set[str]:
    return {part for part in value.lower().replace("&", " ").split() if len(part) > 1}


def _best_name_match(rows, name: str):
    needle = " ".join(name.strip().lower().split())
    if not needle:
        return None
    for row in rows:
        if " ".join(row.name.lower().split()) == needle:
            return row
    wanted = _tokens(needle)
    best, best_score = None, 0
    for row in rows:
        score = len(wanted & _tokens(row.name))
        if score > best_score:
            best, best_score = row, score
    return best if best_score else None


def create_account(payload: AccountCreate) -> dict:
    with session_scope() as session:
        _validate_allocations(session, payload.allocations)
        account = TraderAccount(
            name=payload.name.strip(), emoji=payload.emoji or "🦈", bio=payload.bio or "",
            starting_cash=payload.starting_cash,
        )
        session.add(account)
        session.flush()
        for a in payload.allocations:
            if a.weight > 0:
                session.add(AccountAllocation(account_id=account.id, strategy_id=a.strategy_id, weight=a.weight))
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
        account = session.get(TraderAccount, account_id)
        if not account or account.status != "active":
            raise NotFoundError(f"Trader account {account_id} not found")
        return {"account": _account_view(account, _strategies_map(session, account))}


def update_account(account_id: int, payload: AccountUpdate) -> dict:
    data = payload.model_dump(exclude_unset=True)
    with session_scope() as session:
        account = session.get(TraderAccount, account_id)
        if not account or account.status != "active":
            raise NotFoundError(f"Trader account {account_id} not found")
        if "name" in data and data["name"]:
            account.name = data["name"].strip()
        for field in ("emoji", "bio", "starting_cash"):
            if field in data and data[field] is not None:
                setattr(account, field, data[field])
        if "allocations" in data and data["allocations"] is not None:
            _validate_allocations(session, payload.allocations)
            for existing in list(account.allocations):
                session.delete(existing)
            session.flush()
            for a in payload.allocations:
                if a.weight > 0:
                    session.add(AccountAllocation(account_id=account.id, strategy_id=a.strategy_id, weight=a.weight))
        session.flush()
        session.refresh(account)
        return {"account": _account_view(account, _strategies_map(session, account))}


def delete_account(account_id: int) -> dict:
    with session_scope() as session:
        account = session.get(TraderAccount, account_id)
        if not account or account.status != "active":
            raise NotFoundError(f"Trader account {account_id} not found")
        account.status = "archived"
    return {"deleted": account_id}


def assign_strategy_to_account(*, account_name: str, strategy_name: str, weight: float) -> dict:
    """Set one strategy allocation on an active simulated trader account."""
    if weight <= 0 or weight > 100:
        raise ValidationError("Allocation weight must be between 0 and 100")
    with session_scope() as session:
        accounts = session.query(TraderAccount).filter_by(status="active").all()
        account = _best_name_match(accounts, account_name)
        if account is None:
            raise NotFoundError(f"Trader account '{account_name}' not found")

        strategies = session.query(TradingStrategy).filter_by(status="active").all()
        strategy = _best_name_match(strategies, strategy_name)
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


def account_performance(account_id: int, start: date | None = None, end: date | None = None) -> dict:
    if start is None or end is None:
        start, end = _default_window()
    with session_scope() as session:
        account = session.get(TraderAccount, account_id)
        if not account or account.status != "active":
            raise NotFoundError(f"Trader account {account_id} not found")
        strategies = _strategies_map(session, account)
        starting_cash = float(account.starting_cash)
        allocs = [(a.strategy_id, a.weight, _strategy_view(strategies[a.strategy_id]))
                  for a in account.allocations if a.strategy_id in strategies and a.weight > 0]

    invested_dollars = sum(starting_cash * w / 100 for _, w, _ in allocs)
    cash_dollars = max(0.0, starting_cash - invested_dollars)

    per: list[dict] = []
    warnings: list[str] = []
    all_dates: set[str] = set()
    for sid, weight, view in allocs:
        dollars = starting_cash * weight / 100
        tickers = normalize_tickers(view.get("parameters", {}).get("tickers", []))
        try:
            res = execute_backtest(
                strategy=view, tickers=tickers, start_date=start, end_date=end,
                starting_cash=dollars, benchmark="SPY",
            )
        except Exception as exc:  # noqa: BLE001 — a single broken sleeve shouldn't kill the account
            warnings.append(f"{view['name']}: {exc}")
            continue
        curve = res.get("equity_curve") or []
        dates = [str(p["date"]) for p in curve]
        all_dates.update(dates)
        eq = {str(p["date"]): float(p["equity"]) for p in curve}
        bm = {str(p["date"]): float(p["benchmark_equity"]) for p in curve if p.get("benchmark_equity") is not None}
        final = curve[-1]["equity"] if curve else dollars
        per.append({
            "strategy_id": sid, "name": view["name"], "category": view["category"],
            "weight": weight, "dollars": round(dollars, 2),
            "final": round(final, 2), "pnl": round(final - dollars, 2),
            "return_pct": round((final / dollars - 1) * 100, 2) if dollars else 0.0,
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
        [{k: p[k] for k in ("strategy_id", "name", "category", "weight", "dollars", "final", "pnl", "return_pct")} for p in per],
        key=lambda c: c["pnl"], reverse=True,
    )

    return {
        "account_id": account_id,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "starting_cash": starting_cash,
        "cash_dollars": round(cash_dollars, 2),
        "current_value": round(current, 2),
        "total_return": round(total_return, 4),
        "benchmark_return": round(bench_return, 4),
        "alpha": round(total_return - bench_return, 4),
        "max_drawdown": round(dd, 4),
        "equity": _downsample(blended),
        "contributions": contributions,
        "warnings": list(dict.fromkeys(warnings))[:4],
    }
