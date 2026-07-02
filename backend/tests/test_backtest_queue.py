"""Async backtest job queue: enqueue → claim → execute → poll, dedupe, cancel,
and the boot-time interrupted-job sweep. Uses fixture data — no network."""
from datetime import date

from app.paper_trading import service
from app.paper_trading.schemas import BacktestRequest, StrategyCreate


def _rule_strategy() -> int:
    created = service.create_strategy(StrategyCreate(
        category="short_term",
        name="Test Queue Rule",
        description="queue lifecycle fixture",
        parameters={
            "tickers": ["AAPL"],
            "rules": {
                "instrument": "AAPL", "direction": "long",
                "signal": {"type": "new_high", "reference": "AAPL"},
                "take_profit_pct": 0.1, "stop_loss_pct": 0.05,
            },
        },
    ))
    return created["strategy"]["id"]


def _request(strategy_id: int, *, start=date(2024, 1, 2), end=date(2024, 6, 28)) -> BacktestRequest:
    return BacktestRequest(strategy_id=strategy_id, start_date=start, end_date=end,
                           starting_cash=10000.0, use_fixture_data=True, queue=True)


def test_queue_lifecycle_enqueue_dedupe_execute():
    sid = _rule_strategy()
    queued = service.enqueue_backtest(_request(sid))["run"]
    assert queued["status"] == "queued"
    assert queued["metrics"] == {}

    # Identical pending work dedupes onto the same job instead of stacking runs.
    again = service.enqueue_backtest(_request(sid))["run"]
    assert again["id"] == queued["id"]

    claimed = service.claim_next_queued_backtest()
    assert claimed == queued["id"]
    assert service.get_backtest(claimed)["run"]["status"] == "running"

    service.execute_queued_backtest(claimed)
    done = service.get_backtest(claimed)["run"]
    assert done["status"] == "completed"
    assert done["metrics"].get("total_return") is not None
    assert done["equity_curve"], "queued execution must persist the equity curve"
    assert done["integrity"], "queued execution must persist the integrity report"


def test_queue_cancel_and_interrupted_sweep():
    sid = _rule_strategy()
    queued = service.enqueue_backtest(_request(sid, start=date(2023, 1, 2), end=date(2023, 6, 30)))["run"]
    cancelled = service.cancel_backtest(queued["id"])["run"]
    assert cancelled["status"] == "cancelled"
    assert service.claim_next_queued_backtest() is None  # cancelled jobs are never claimed

    # A run stuck in 'running' (killed process) is failed on boot, not left forever.
    queued2 = service.enqueue_backtest(_request(sid, start=date(2022, 1, 3), end=date(2022, 6, 30)))["run"]
    assert service.claim_next_queued_backtest() == queued2["id"]
    assert service.fail_interrupted_backtests() == 1
    swept = service.get_backtest(queued2["id"])["run"]
    assert swept["status"] == "failed"
    assert swept["warnings"]


def test_enqueue_fails_fast_on_bad_strategy():
    import pytest
    from app.core.errors import NotFoundError
    with pytest.raises(NotFoundError):
        service.enqueue_backtest(_request(999999))
