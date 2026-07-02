"""Paper trading services: strategy CRUD and backtest persistence."""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from math import sqrt
from typing import Any

from ..backtesting.engine import run_backtest as execute_backtest
from ..core.errors import NotFoundError, ValidationError
from ..db import session_scope
from ..models.paper_trading import (
    BacktestEquityPoint,
    BacktestRun,
    BacktestTrade,
    TradingStrategy,
)
from .schemas import BacktestRequest, ParameterSweepRequest, StrategyCreate, StrategyUpdate, normalize_tickers
from .seed_catalog import CATEGORIES, SEED_STRATEGIES, with_defaults
from .validation import validate_or_raise, validate_strategy_config


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _unique_slug(session, name: str, *, prefix: str = "") -> str:
    base = _slug(f"{prefix}-{name}" if prefix else name) or "strategy"
    slug = base
    index = 2
    while session.query(TradingStrategy).filter_by(slug=slug).first():
        slug = f"{base}-{index}"
        index += 1
    return slug


def _strategy_view(strategy: TradingStrategy) -> dict:
    return {
        "id": strategy.id,
        "category": strategy.category,
        "name": strategy.name,
        "slug": strategy.slug,
        "origin": strategy.origin,
        "status": strategy.status,
        "description": strategy.description or "",
        "history": strategy.history or "",
        "methodology": strategy.methodology or "",
        "parameters": strategy.parameters_json or {},
        "defaults": strategy.defaults_json or {},
        "metrics": strategy.metrics_json or {},
        "caveats": strategy.caveats_json or [],
        "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
        "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
    }


def ensure_seeded() -> None:
    with session_scope() as session:
        for item in SEED_STRATEGIES:
            seed = with_defaults(item)
            slug = _slug(seed["name"])
            existing = session.query(TradingStrategy).filter_by(slug=slug).first()
            if existing:
                # The catalogue is the source of truth for seeded *content* — sync text and
                # parameters so deployed DBs pick up model upgrades, but never touch
                # metrics_json: it accumulates the user's real backtest headline.
                if existing.origin == "seeded" and existing.status == "active":
                    existing.category = seed["category"]
                    existing.description = seed.get("description", "")
                    existing.history = seed.get("history", "")
                    existing.methodology = seed.get("methodology", "")
                    existing.parameters_json = seed.get("parameters", {})
                    existing.defaults_json = seed.get("defaults", {})
                    existing.caveats_json = seed.get("caveats", [])
                continue
            session.add(TradingStrategy(
                category=seed["category"],
                name=seed["name"],
                slug=slug,
                origin="seeded",
                description=seed.get("description", ""),
                history=seed.get("history", ""),
                methodology=seed.get("methodology", ""),
                parameters_json=seed.get("parameters", {}),
                defaults_json=seed.get("defaults", {}),
                metrics_json=seed.get("metrics", {}),
                caveats_json=seed.get("caveats", []),
            ))


def list_categories() -> dict:
    ensure_seeded()
    with session_scope() as session:
        strategies = session.query(TradingStrategy).filter_by(status="active").order_by(TradingStrategy.name.asc()).all()
        by_category: dict[str, list[dict]] = {category["id"]: [] for category in CATEGORIES}
        for strategy in strategies:
            by_category.setdefault(strategy.category, []).append(_strategy_view(strategy))
        return {"categories": [{**category, "strategies": by_category.get(category["id"], [])} for category in CATEGORIES]}


def list_strategies() -> dict:
    ensure_seeded()
    with session_scope() as session:
        rows = session.query(TradingStrategy).filter_by(status="active").order_by(TradingStrategy.name.asc()).all()
        return {"strategies": [_strategy_view(row) for row in rows]}


def get_strategy(strategy_id: int) -> dict:
    ensure_seeded()
    with session_scope() as session:
        strategy = session.get(TradingStrategy, strategy_id)
        if not strategy or strategy.status != "active":
            raise NotFoundError(f"Strategy {strategy_id} not found")
        return {"strategy": _strategy_view(strategy)}


def create_strategy(payload: StrategyCreate) -> dict:
    data = payload.model_dump()
    validation = validate_or_raise(data["category"], data["parameters"])
    data["parameters"] = validation["parameters"]
    with session_scope() as session:
        strategy = TradingStrategy(
            category=data["category"],
            name=data["name"].strip(),
            slug=_unique_slug(session, data["name"]),
            origin="user",
            description=data["description"],
            history=data["history"],
            methodology=data["methodology"],
            parameters_json=data["parameters"],
            defaults_json=data["defaults"] or data["parameters"],
            metrics_json=data["metrics"],
            caveats_json=data["caveats"],
        )
        session.add(strategy)
        session.flush()
        return {"strategy": _strategy_view(strategy)}


def update_strategy(strategy_id: int, payload: StrategyUpdate) -> dict:
    data = payload.model_dump(exclude_unset=True)
    with session_scope() as session:
        strategy = session.get(TradingStrategy, strategy_id)
        if not strategy or strategy.status != "active":
            raise NotFoundError(f"Strategy {strategy_id} not found")
        if strategy.origin == "seeded":
            raise ValidationError("Seeded strategies must be cloned before editing")
        if "name" in data and data["name"]:
            strategy.name = data["name"].strip()
        if "category" in data or "parameters" in data:
            category = data.get("category") or strategy.category
            parameters = data.get("parameters") if "parameters" in data else (strategy.parameters_json or {})
            validation = validate_or_raise(category, parameters)
            data["parameters"] = validation["parameters"]
        for source, target in [
            ("category", "category"),
            ("description", "description"),
            ("history", "history"),
            ("methodology", "methodology"),
        ]:
            if source in data and data[source] is not None:
                setattr(strategy, target, data[source])
        for source, target in [
            ("parameters", "parameters_json"),
            ("defaults", "defaults_json"),
            ("metrics", "metrics_json"),
            ("caveats", "caveats_json"),
        ]:
            if source in data and data[source] is not None:
                setattr(strategy, target, data[source])
        session.flush()
        return {"strategy": _strategy_view(strategy)}


def clone_strategy(strategy_id: int) -> dict:
    ensure_seeded()
    with session_scope() as session:
        source = session.get(TradingStrategy, strategy_id)
        if not source or source.status != "active":
            raise NotFoundError(f"Strategy {strategy_id} not found")
        clone = TradingStrategy(
            category=source.category,
            name=f"{source.name} Copy",
            slug=_unique_slug(session, source.name, prefix="copy"),
            origin="user",
            description=source.description,
            history=source.history,
            methodology=source.methodology,
            parameters_json=source.parameters_json or {},
            defaults_json=source.defaults_json or {},
            # A clone has no runs of its own — inheriting the source's backtest
            # headline would show results this strategy never produced.
            metrics_json={},
            caveats_json=source.caveats_json or [],
        )
        session.add(clone)
        session.flush()
        return {"strategy": _strategy_view(clone)}


def validate_strategy(payload) -> dict:
    return validate_strategy_config(payload.category, payload.parameters)


def _accounts_using_strategy(session, strategy_id: int) -> list[str]:
    """Names of active trader accounts still allocated to this strategy."""
    from ..models.paper_trading import AccountAllocation, TraderAccount
    rows = (session.query(TraderAccount.name)
            .join(AccountAllocation, AccountAllocation.account_id == TraderAccount.id)
            .filter(AccountAllocation.strategy_id == strategy_id, TraderAccount.status == "active")
            .distinct().all())
    return [name for (name,) in rows]


def delete_strategy(strategy_id: int) -> dict:
    """Archive a user strategy. Archived strategies leave the active list but keep
    simulating in any trader still allocated to them (that's why we report who) —
    and stay recoverable via ``unarchive_strategy``."""
    with session_scope() as session:
        strategy = session.get(TradingStrategy, strategy_id)
        if not strategy or strategy.status != "active":
            raise NotFoundError(f"Strategy {strategy_id} not found")
        if strategy.origin == "seeded":
            raise ValidationError("Seeded strategies cannot be archived; clone them first")
        strategy.status = "archived"
        in_use = _accounts_using_strategy(session, strategy_id)
    return {"archived": strategy_id, "in_use_by": in_use}


def unarchive_strategy(strategy_id: int) -> dict:
    """Restore an archived strategy to the active catalogue."""
    with session_scope() as session:
        strategy = session.get(TradingStrategy, strategy_id)
        if not strategy:
            raise NotFoundError(f"Strategy {strategy_id} not found")
        if strategy.status == "active":
            return {"strategy": _strategy_view(strategy)}
        if strategy.status != "archived":
            raise ValidationError(f"Strategy {strategy_id} is {strategy.status} and cannot be restored")
        # A slug collision means an active strategy already owns this name.
        clash = (session.query(TradingStrategy)
                 .filter(TradingStrategy.slug == strategy.slug, TradingStrategy.status == "active",
                         TradingStrategy.id != strategy.id).first())
        if clash:
            raise ValidationError(f"An active strategy already uses the name “{strategy.name}” — rename it first")
        strategy.status = "active"
        return {"strategy": _strategy_view(strategy)}


def list_archived_strategies() -> dict:
    with session_scope() as session:
        rows = (session.query(TradingStrategy).filter_by(status="archived", origin="user")
                .order_by(TradingStrategy.name.asc()).all())
        return {"strategies": [_strategy_view(row) for row in rows]}


def _run_view(run: BacktestRun) -> dict:
    inputs = run.inputs_json or {}
    return {
        "id": run.id,
        "strategy_id": run.strategy_id,
        "name": run.name,
        "start_date": run.start_date.isoformat(),
        "end_date": run.end_date.isoformat(),
        "starting_cash": run.starting_cash,
        "status": run.status or "completed",  # legacy rows predate the job queue
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "inputs": inputs,
        "strategy_snapshot": inputs.get("strategy_snapshot"),
        "metrics": run.metrics_json or {},
        "warnings": run.warnings_json or [],
        "integrity": inputs.get("integrity"),
        "holdings": inputs.get("holdings") or [],
        "trades": [{
            "date": trade.trade_date.isoformat(),
            "ticker": trade.ticker,
            "side": trade.side,
            "quantity": trade.quantity,
            "price": trade.price,
            "value": trade.value,
            "reason": trade.reason,
        } for trade in run.trades],
        "equity_curve": [{
            "date": point.date.isoformat(),
            "cash": point.cash,
            "equity": point.equity,
            "benchmark_equity": point.benchmark_equity,
        } for point in run.equity_points],
    }


def _inputs_with_snapshot(payload: dict[str, Any], strategy_view: dict, extra: dict[str, Any] | None = None) -> dict:
    inputs = dict(payload)
    inputs["strategy_snapshot"] = deepcopy(strategy_view)
    if extra:
        inputs.update(extra)
    return inputs


def _persist_backtest_result(
    *,
    strategy_id: int | None,
    name: str,
    start_date: date,
    end_date: date,
    starting_cash: float,
    inputs: dict[str, Any],
    result: dict,
    run_id: int | None = None,
) -> int:
    # Final allocation travels with the run so polled/listed runs can render it.
    inputs = {**inputs, "holdings": _json_dates(result.get("holdings") or [])}
    with session_scope() as session:
        if run_id is not None:
            # Queued job completing — fill the existing row instead of creating one.
            run = session.get(BacktestRun, run_id)
            if run is None:
                raise NotFoundError(f"Backtest {run_id} not found")
            run.strategy_id = strategy_id
            run.name = name
            run.start_date = start_date
            run.end_date = end_date
            run.starting_cash = starting_cash
            run.inputs_json = inputs
            run.metrics_json = result["metrics"]
            run.warnings_json = result["warnings"]
            run.status = "completed"
            session.query(BacktestTrade).filter_by(run_id=run.id).delete(synchronize_session=False)
            session.query(BacktestEquityPoint).filter_by(run_id=run.id).delete(synchronize_session=False)
        else:
            run = BacktestRun(
                strategy_id=strategy_id,
                name=name,
                start_date=start_date,
                end_date=end_date,
                starting_cash=starting_cash,
                status="completed",
                inputs_json=inputs,
                metrics_json=result["metrics"],
                warnings_json=result["warnings"],
            )
            session.add(run)
        session.flush()
        for trade in result["trades"]:
            session.add(BacktestTrade(
                run_id=run.id,
                trade_date=trade["date"],
                ticker=trade["ticker"],
                side=trade["side"],
                quantity=trade["quantity"],
                price=trade["price"],
                value=trade["value"],
                reason=trade["reason"],
            ))
        for point in result["equity_curve"]:
            session.add(BacktestEquityPoint(
                run_id=run.id,
                date=point["date"],
                cash=point["cash"],
                equity=point["equity"],
                benchmark_equity=point["benchmark_equity"],
            ))
        session.flush()
        return run.id


def _resolve_strategy_view(payload: BacktestRequest) -> dict:
    """Load + validate the strategy a backtest request targets (fail-fast)."""
    with session_scope() as session:
        if payload.strategy_id:
            strategy = session.get(TradingStrategy, payload.strategy_id)
            if not strategy or strategy.status != "active":
                raise NotFoundError(f"Strategy {payload.strategy_id} not found")
            strategy_view = _strategy_view(strategy)
        elif payload.strategy:
            strategy_view = payload.strategy.model_dump()
        else:
            raise ValidationError("strategy_id or inline strategy is required")
    validation = validate_or_raise(strategy_view["category"], strategy_view.get("parameters", {}))
    strategy_view["parameters"] = validation["parameters"]
    return strategy_view


def run_backtest(payload: BacktestRequest, *, run_id: int | None = None) -> dict:
    ensure_seeded()
    tickers = normalize_tickers(payload.tickers)
    strategy_view = _resolve_strategy_view(payload)

    result = execute_backtest(
        strategy=strategy_view,
        tickers=tickers,
        start_date=payload.start_date,
        end_date=payload.end_date,
        starting_cash=payload.starting_cash,
        transaction_cost_bps=payload.transaction_cost_bps,
        slippage_bps=payload.slippage_bps,
        benchmark=payload.benchmark,
        use_fixture_data=payload.use_fixture_data,
    )
    run_id = _persist_backtest_result(
        strategy_id=payload.strategy_id,
        name=f"{strategy_view['name']} {payload.start_date} to {payload.end_date}",
        start_date=payload.start_date,
        end_date=payload.end_date,
        starting_cash=payload.starting_cash,
        inputs=_inputs_with_snapshot(payload.model_dump(mode="json"), strategy_view,
                                     {"integrity": result.get("integrity")}),
        result=result,
        run_id=run_id,
    )

    if payload.persist_headline and payload.strategy_id:
        _store_headline(payload.strategy_id, result, payload.start_date, payload.end_date)

    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        return {"run": _run_view(run), "served_by": result["served_by"], "holdings": _json_dates(result["holdings"])}


# --------------------------------------------------------------------------- #
# Async backtest jobs                                                          #
#                                                                              #
# POST /backtests with queue=true creates a queued BacktestRun row and returns #
# immediately; a single in-process worker (main.py) executes jobs under the    #
# engine lock and the client polls GET /backtests/{id}. This keeps long runs   #
# alive across proxy timeouts (Next dev ~30s, Render edge ~100s) and stops     #
# duplicate concurrent runs of the same strategy/window.                       #
# --------------------------------------------------------------------------- #

def enqueue_backtest(payload: BacktestRequest) -> dict:
    ensure_seeded()
    strategy_view = _resolve_strategy_view(payload)  # fail-fast before queuing
    with session_scope() as session:
        if payload.strategy_id:
            # Dedupe: identical pending work returns the existing job instead of stacking
            # multi-minute engine runs behind the lock.
            existing = session.query(BacktestRun).filter(
                BacktestRun.strategy_id == payload.strategy_id,
                BacktestRun.status.in_(("queued", "running")),
                BacktestRun.start_date == payload.start_date,
                BacktestRun.end_date == payload.end_date,
            ).first()
            if existing:
                return {"run": _run_view(existing)}
        run = BacktestRun(
            strategy_id=payload.strategy_id,
            name=f"{strategy_view['name']} {payload.start_date} to {payload.end_date}",
            start_date=payload.start_date,
            end_date=payload.end_date,
            starting_cash=payload.starting_cash,
            status="queued",
            inputs_json=_inputs_with_snapshot(payload.model_dump(mode="json"), strategy_view),
            metrics_json={},
            warnings_json=[],
        )
        session.add(run)
        session.flush()
        return {"run": _run_view(run)}


def claim_next_queued_backtest() -> int | None:
    """Oldest queued run id, marked running. Single-worker, so no claim race."""
    with session_scope() as session:
        run = session.query(BacktestRun).filter_by(status="queued").order_by(BacktestRun.id.asc()).first()
        if run is None:
            return None
        run.status = "running"
        return run.id


def execute_queued_backtest(run_id: int) -> None:
    """Execute one claimed job to completion (worker thread)."""
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        if run is None or run.status != "running":
            return
        request_data = {k: v for k, v in (run.inputs_json or {}).items()
                        if k not in ("strategy_snapshot", "integrity", "holdings")}
    try:
        payload = BacktestRequest(**request_data)
        run_backtest(payload, run_id=run_id)
    except Exception as exc:  # noqa: BLE001 — the job row is the error surface
        with session_scope() as session:
            run = session.get(BacktestRun, run_id)
            if run is not None:
                run.status = "failed"
                message = getattr(exc, "message", None) or str(exc) or "Backtest failed"
                run.warnings_json = [message]


def fail_interrupted_backtests() -> int:
    """Boot-time sweep: anything still 'running' was killed by a restart."""
    with session_scope() as session:
        rows = session.query(BacktestRun).filter_by(status="running").all()
        for run in rows:
            run.status = "failed"
            run.warnings_json = ["Backtest interrupted by a server restart — run it again."]
        return len(rows)


def cancel_backtest(run_id: int) -> dict:
    """Cancel a still-queued run. Running jobs finish (the engine has no safe
    mid-run abort); completed/failed runs are returned unchanged."""
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        if not run:
            raise NotFoundError(f"Backtest {run_id} not found")
        if run.status == "queued":
            run.status = "cancelled"
        return {"run": _run_view(run)}


def list_backtests(*, strategy_id: int | None = None, limit: int = 20) -> dict:
    with session_scope() as session:
        q = session.query(BacktestRun).order_by(BacktestRun.id.desc())
        if strategy_id:
            q = q.filter(BacktestRun.strategy_id == strategy_id)
        rows = q.limit(max(1, min(int(limit), 100))).all()
        return {"runs": [{
            "id": run.id,
            "strategy_id": run.strategy_id,
            "name": run.name,
            "start_date": run.start_date.isoformat() if run.start_date else None,
            "end_date": run.end_date.isoformat() if run.end_date else None,
            "status": run.status or "completed",
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "metrics": run.metrics_json or {},
            "sweep": bool((run.inputs_json or {}).get("sweep")),
        } for run in rows]}


def _set_parameter(parameters: dict[str, Any], path: str, value: float) -> None:
    parts = [part.strip() for part in path.split(".") if part.strip()]
    if not parts:
        raise ValidationError("Sweep parameter path is required")
    target = parameters
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            child = {}
            target[part] = child
        target = child
    target[parts[-1]] = value


def _daily_sharpe(curve: list[dict]) -> float | None:
    returns = []
    for idx in range(1, len(curve)):
        prev = float(curve[idx - 1].get("equity") or 0)
        cur = float(curve[idx].get("equity") or 0)
        if prev > 0:
            returns.append(cur / prev - 1)
    if len(returns) < 2:
        return None
    avg = sum(returns) / len(returns)
    variance = sum((value - avg) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    return (avg / (variance ** 0.5)) * sqrt(252)


def _sweep_metrics(result: dict, starting_cash: float) -> dict:
    metrics = dict(result.get("metrics") or {})
    trades = result.get("trades") or []
    holdings = result.get("holdings") or []
    turnover = sum(abs(float(trade.get("value") or 0)) for trade in trades) / starting_cash if starting_cash else 0
    exposure = sum(
        float(holding.get("weight") or 0)
        for holding in holdings
        if str(holding.get("ticker", "")).upper() != "CASH"
    )
    metrics["sharpe"] = _daily_sharpe(result.get("equity_curve") or [])
    metrics["turnover"] = turnover
    metrics["exposure"] = exposure
    return metrics


def run_parameter_sweep(payload: ParameterSweepRequest) -> dict:
    ensure_seeded()
    if payload.end_date <= payload.start_date:
        raise ValidationError("Backtest end_date must be after start_date")

    with session_scope() as session:
        strategy = session.get(TradingStrategy, payload.strategy_id)
        if not strategy or strategy.status != "active":
            raise NotFoundError(f"Strategy {payload.strategy_id} not found")
        base_strategy = _strategy_view(strategy)

    rows = []
    base_inputs = payload.model_dump(mode="json")
    for value in payload.values:
        variant = deepcopy(base_strategy)
        variant["parameters"] = deepcopy(base_strategy.get("parameters") or {})
        _set_parameter(variant["parameters"], payload.parameter, value)
        validation = validate_or_raise(variant["category"], variant["parameters"])
        variant["parameters"] = validation["parameters"]
        tickers = normalize_tickers(variant.get("parameters", {}).get("tickers", []))

        result = execute_backtest(
            strategy=variant,
            tickers=tickers,
            start_date=payload.start_date,
            end_date=payload.end_date,
            starting_cash=payload.starting_cash,
            transaction_cost_bps=payload.transaction_cost_bps,
            slippage_bps=payload.slippage_bps,
            benchmark=payload.benchmark,
            use_fixture_data=payload.use_fixture_data,
        )
        metrics = _sweep_metrics(result, payload.starting_cash)
        run_id = _persist_backtest_result(
            strategy_id=payload.strategy_id,
            name=f"{variant['name']} sweep {payload.parameter}={value:g}",
            start_date=payload.start_date,
            end_date=payload.end_date,
            starting_cash=payload.starting_cash,
            inputs=_inputs_with_snapshot(
                base_inputs,
                variant,
                {"sweep": {"parameter": payload.parameter, "value": value, "rank_by": payload.rank_by},
                 "integrity": result.get("integrity")},
            ),
            result={**result, "metrics": metrics},
        )
        rows.append({
            "run_id": run_id,
            "parameter": payload.parameter,
            "value": value,
            "metrics": metrics,
            "parameters": variant["parameters"],
            "warnings": result.get("warnings", []),
        })

    reverse = payload.rank_by != "turnover"
    rows.sort(key=lambda row: row["metrics"].get(payload.rank_by) if row["metrics"].get(payload.rank_by) is not None else float("-inf"), reverse=reverse)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx

    return {
        "sweep": {
            "strategy_id": payload.strategy_id,
            "strategy_name": base_strategy["name"],
            "parameter": payload.parameter,
            "rank_by": payload.rank_by,
            "runs": rows,
        }
    }


def _downsample(points: list[dict], key: str, n: int = 90) -> list[dict]:
    pts = [p for p in points if p.get(key) is not None]
    if not pts:
        return []
    if len(pts) <= n:
        return [{"d": str(p["date"]), "v": round(float(p[key]), 2)} for p in pts]
    step = (len(pts) - 1) / (n - 1)
    out = []
    for i in range(n):
        p = pts[min(round(i * step), len(pts) - 1)]
        out.append({"d": str(p["date"]), "v": round(float(p[key]), 2)})
    return out


def _store_headline(strategy_id: int, result: dict, start: date, end: date) -> None:
    """Persist a compact backtest preview (metrics + downsampled equity) onto the
    strategy so cards/detail show real, backtested numbers instead of mock series."""
    curve = result.get("equity_curve") or []
    metrics = dict(result.get("metrics") or {})
    bench_first = curve[0].get("benchmark_equity") if curve else None
    bench_last = curve[-1].get("benchmark_equity") if curve else None
    bench_ret = (bench_last / bench_first - 1) if (bench_first and bench_last) else None
    if bench_ret is not None and metrics.get("total_return") is not None:
        metrics["alpha"] = metrics["total_return"] - bench_ret
        metrics["benchmark_return"] = bench_ret
    headline = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "metrics": metrics,
        "equity": _downsample(curve, "equity"),
        "benchmark": _downsample(curve, "benchmark_equity"),
        "warnings": result.get("warnings", [])[:2],
    }
    with session_scope() as session:
        strategy = session.get(TradingStrategy, strategy_id)
        if not strategy:
            return
        merged = dict(strategy.metrics_json or {})
        merged["_backtest"] = headline
        # also surface the headline returns at the top level for legacy readers
        if metrics.get("total_return") is not None:
            merged["backtested_return"] = round(metrics["total_return"], 4)
        if metrics.get("max_drawdown") is not None:
            merged["max_drawdown"] = round(metrics["max_drawdown"], 4)
        if metrics.get("win_rate") is not None:
            merged["win_rate"] = round(metrics["win_rate"], 4)
        strategy.metrics_json = merged
        session.flush()


def get_backtest(run_id: int) -> dict:
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        if not run:
            raise NotFoundError(f"Backtest {run_id} not found")
        return {"run": _run_view(run)}


def _json_dates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        copy = dict(item)
        for key, value in list(copy.items()):
            if isinstance(value, date):
                copy[key] = value.isoformat()
        out.append(copy)
    return out
