import os
import tempfile

# --- Test isolation --------------------------------------------------------
# The SQLAlchemy engine binds settings.database_url AT IMPORT TIME, so these
# overrides must run before any `app.` import. Without them the suite reads and
# WRITES the real dev atlas.db: the name-based cleanup below then orphans
# backtest_runs rows, and SQLite id reuse attaches those ghosts to future real
# strategies. The cache override keeps tests from poisoning the dev dead-ticker
# skiplist and provider-quota counters.
_TEST_TMP = tempfile.mkdtemp(prefix="atlas-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_TMP}/test.db")
os.environ.setdefault("CACHE_DIR", f"{_TEST_TMP}/cache")

import pytest

from app.core.rate_limit import reset_rate_limits
from app.db import init_db, session_scope
from app.db import CompanySnapshot, PitFundamental, Watchlist
from app.models.assistant import AssistantMessage, AssistantPendingAction, AssistantSession
from app.models.paper_trading import BacktestRun, TraderAccount, TradingStrategy
from app.models.valuation import ValuationResult

init_db()  # the fresh temp DB needs its tables before any test touches it


@pytest.fixture(autouse=True)
def cleanup_feature_test_records():
    reset_rate_limits()
    yield
    with session_scope() as session:
        for run in session.query(BacktestRun).filter(BacktestRun.name.like("Test%")).all():
            session.delete(run)
        accounts = session.query(TraderAccount).filter(
            TraderAccount.name.in_([
                "Assistant Assign Trader",
                "Assistant Generated Trader",
                "Assistant Orchestrated Trader",
                "Assistant Performance Trader",
                "Assistant Profile Reader",
                "Assistant Rebalance Trader",
                "Assistant Retry Trader",
                "Lifecycle Trader",
                "Archive Context Trader",
                "Attribution Trader",
                "QA Lifecycle Trader",
                "Test Trader",
                "Test Full QA Trader",
                "Renamed Trader",
                "Test Whale",
            ])
        ).all()
        for account in accounts:
            session.delete(account)
        strategies = session.query(TradingStrategy).filter(
            TradingStrategy.name.in_([
                "Test Quality Clone",
                "Updated Quality Clone",
                "Test Quality Clone Copy",
                "Updated Quality Clone Copy",
                "Test Fixture Momentum",
                "Test Full QA Strategy",
                "Test Full QA Strategy Saved",
                "Test Signal Rule",
                "Test Snapshot Strategy",
                "Test Sweep Strategy",
                "Acct Test Strategy",
                "Archive Context Strategy",
                "Lifecycle Trader A",
                "Lifecycle Trader B",
                "Attribution A",
                "Attribution B",
                "AI FCF Test",
                "Assistant Assign Strategy",
                "Assistant Clone Source",
                "Assistant Clone Source Copy",
                "Assistant Generated Model",
                "Assistant Orchestrated Model",
                "Assistant Performance Strategy",
                "Assistant Rebalance A",
                "Assistant Rebalance B",
                "Assistant Retry Model",
                "Test Queue Rule",
            ])
        ).all()
        for strategy in strategies:
            session.delete(strategy)
        sessions = session.query(AssistantSession).filter(
            AssistantSession.title.in_([
                "Test Strategy Chat",
                "Test Action Chat",
                "Test Assign Chat",
                "Test Profiles Chat",
                "Test Performance Chat",
                "Test Clone Chat",
                "Test Rebalance Chat",
                "Test Copilot Workflow Chat",
                "Test Orchestration Chat",
                "Test Orchestration Reject Chat",
                "Test Orchestration Retry Chat",
                "Rate Limit 1",
                "Rate Limit 2",
                "Strategy chat",
            ])
        ).all()
        session_ids = [row.id for row in sessions]
        if session_ids:
            session.query(AssistantMessage).filter(AssistantMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            session.query(AssistantPendingAction).filter(AssistantPendingAction.session_id.in_(session_ids)).delete(synchronize_session=False)
        for assistant_session in sessions:
            session.delete(assistant_session)
        session.query(ValuationResult).filter(ValuationResult.ticker.in_(["TST", "NEG"])).delete(synchronize_session=False)
        session.query(CompanySnapshot).filter(CompanySnapshot.ticker.in_(["AAA", "BBB", "CCC", "FAIL"])).delete(synchronize_session=False)
        session.query(PitFundamental).filter(PitFundamental.ticker.in_(["X", "AAA", "BBB"])).delete(synchronize_session=False)
        watchlists = session.query(Watchlist).filter(Watchlist.name.in_(["Test Warm Watchlist"])).all()
        for watchlist in watchlists:
            session.delete(watchlist)
