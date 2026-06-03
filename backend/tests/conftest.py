import pytest

from app.db import session_scope
from app.models.assistant import AssistantMessage, AssistantPendingAction, AssistantSession
from app.models.paper_trading import BacktestRun, PaperPortfolio, TraderAccount, TradingStrategy


@pytest.fixture(autouse=True)
def cleanup_feature_test_records():
    yield
    with session_scope() as session:
        for portfolio in session.query(PaperPortfolio).filter(PaperPortfolio.name.in_(["Fixture Portfolio", "Runnable Portfolio"])).all():
            session.delete(portfolio)
        for run in session.query(BacktestRun).filter(BacktestRun.name.like("Test%")).all():
            session.delete(run)
        accounts = session.query(TraderAccount).filter(
            TraderAccount.name.in_(["Assistant Assign Trader"])
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
                "Test Income Portfolio",
                "Test Run Portfolio",
                "AI FCF Test",
                "Assistant Assign Strategy",
            ])
        ).all()
        for strategy in strategies:
            session.delete(strategy)
        sessions = session.query(AssistantSession).filter(
            AssistantSession.title.in_(["Test Strategy Chat", "Test Action Chat", "Test Assign Chat", "Strategy chat"])
        ).all()
        session_ids = [row.id for row in sessions]
        if session_ids:
            session.query(AssistantMessage).filter(AssistantMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            session.query(AssistantPendingAction).filter(AssistantPendingAction.session_id.in_(session_ids)).delete(synchronize_session=False)
        for assistant_session in sessions:
            session.delete(assistant_session)
