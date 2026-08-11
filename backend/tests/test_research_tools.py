from datetime import date, timedelta

import pytest

from app.assistant import research_tools
from app.core.errors import ValidationError


def test_three_year_price_tool_trims_provider_five_year_fetch(monkeypatch):
    old = (date.today() - timedelta(days=1400)).isoformat()
    inside = (date.today() - timedelta(days=900)).isoformat()
    latest = date.today().isoformat()

    def fake_history(_ticker, *, range, interval):
        assert range == "3y"
        assert interval == "1d"
        return {
            "bars": [
                {"date": old, "close": 50.0, "adjusted_close": 50.0},
                {"date": inside, "close": 100.0, "adjusted_close": 100.0},
                {"date": latest, "close": 125.0, "adjusted_close": 125.0},
            ],
        }, "fixture"

    monkeypatch.setattr(research_tools.prices, "price_history", fake_history)
    result = research_tools.execute("get_price_history", {"ticker": "SPY", "range": "3y"})
    assert [point["date"] for point in result["data"]["points"]] == [inside, latest]
    assert result["data"]["statistics"]["total_return"] == 0.25


def test_research_range_schema_matches_site_ranges():
    tool = next(item for item in research_tools.RESEARCH_TOOLS if item["name"] == "compare_securities")
    values = tool["parameters"]["properties"]["range"]["enum"]
    assert "3y" in values
    assert "2y" not in values
    assert "3mo" not in values


@pytest.mark.parametrize(
    "arguments",
    [
        {"tickers": ["SPY"], "range": "3y"},
        {"tickers": ["SPY", "QQQ"], "range": "2y"},
        {"tickers": ["SPY", "QQQ"], "range": "3y", "sql": "select *"},
    ],
)
def test_tool_arguments_fail_closed_before_execution(monkeypatch, arguments):
    called = False

    def should_not_run(_arguments):
        nonlocal called
        called = True
        return {}

    monkeypatch.setitem(research_tools.EXECUTORS, "compare_securities", should_not_run)
    with pytest.raises(ValidationError):
        research_tools.execute("compare_securities", arguments)
    assert called is False
