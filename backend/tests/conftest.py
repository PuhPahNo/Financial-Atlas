import pytest

from app.db import session_scope
from app.db import CompanySnapshot, Watchlist, WatchlistItem
from app.models.assistant import AssistantMessage, AssistantPendingAction, AssistantSession
from app.models.paper_trading import BacktestRun, PaperPortfolio, TraderAccount, TradingStrategy
from app.models.valuation import ValuationResult


@pytest.fixture(autouse=True)
def cleanup_feature_test_records():
    yield
    with session_scope() as session:
        for portfolio in session.query(PaperPortfolio).filter(PaperPortfolio.name.in_(["Fixture Portfolio", "Runnable Portfolio"])).all():
            session.delete(portfolio)
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
                "Test Income Portfolio",
                "Test Run Portfolio",
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
        watchlists = session.query(Watchlist).filter(Watchlist.name.in_(["Test Warm Watchlist"])).all()
        for watchlist in watchlists:
            session.delete(watchlist)
