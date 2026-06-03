from fastapi.testclient import TestClient

from app.main import app
from auth_helpers import authenticate

client = authenticate(TestClient(app))


def _rule(
    *,
    instrument: str = "SPY",
    direction: str = "long",
    signal: dict | None = None,
    take_profit_pct: float = 0.10,
    stop_loss_pct: float = 0.05,
) -> dict:
    return {
        "tickers": [instrument],
        "rules": {
            "instrument": instrument,
            "direction": direction,
            "signal": signal or {"type": "new_high", "reference": "^GSPC"},
            "take_profit_pct": take_profit_pct,
            "stop_loss_pct": stop_loss_pct,
            "max_hold_days": 30,
        },
    }


def _options_rule() -> dict:
    params = _rule(instrument="AAPL")
    params["synthetic_options"] = {
        "style": "underlying_proxy",
        "underlying": "AAPL",
        "assumption": "Option-like payoff is approximated with underlying closes.",
    }
    return params


def _validate(category: str, parameters: dict):
    return client.post("/api/v1/paper-trading/strategies/validate", json={"category": category, "parameters": parameters})


def test_strategy_validation_endpoint_covers_each_family():
    cases = [
        (
            "long_term",
            _rule(instrument="MSFT"),
            _rule(instrument="MSFT", direction="short"),
        ),
        (
            "short_term",
            _rule(instrument="QQQ", signal={"type": "ma_cross_up", "reference": "QQQ", "fast_days": 20, "slow_days": 50}),
            _rule(instrument="QQQ", signal={"type": "ma_cross_up", "reference": "QQQ", "fast_days": 80, "slow_days": 20}),
        ),
        (
            "short_selling",
            _rule(instrument="TSLA", direction="short", signal={"type": "pct_gain", "reference": "TSLA", "pct": 0.05, "window_days": 10}),
            _rule(instrument="TSLA", direction="long", signal={"type": "pct_gain", "reference": "TSLA", "pct": 0.05, "window_days": 10}),
        ),
        (
            "options",
            _options_rule(),
            _rule(instrument="AAPL"),
        ),
        (
            "income_quality",
            _rule(instrument="JNJ", signal={"type": "pct_drop", "reference": "SPY", "pct": 0.04, "window_days": 15}),
            _rule(instrument="JNJ", direction="short", signal={"type": "pct_drop", "reference": "SPY", "pct": 0.04, "window_days": 15}),
        ),
        (
            "risk_rotation",
            _rule(instrument="SQQQ", signal={"type": "new_high", "reference": "^GSPC"}),
            _rule(instrument="SQQQ", signal={"type": "not_a_signal", "reference": "^GSPC"}),
        ),
    ]

    for category, valid_params, invalid_params in cases:
        valid = _validate(category, valid_params)
        assert valid.status_code == 200
        assert valid.json()["data"]["valid"] is True

        invalid = _validate(category, invalid_params)
        assert invalid.status_code == 200
        payload = invalid.json()["data"]
        assert payload["valid"] is False
        assert payload["issues"], category


def test_invalid_strategy_create_returns_field_level_issues():
    res = client.post(
        "/api/v1/paper-trading/strategies",
        json={
            "category": "short_selling",
            "name": "Invalid Long Short Rule",
            "methodology": "Should not persist.",
            "parameters": _rule(instrument="TSLA", direction="long"),
        },
    )
    assert res.status_code == 400
    body = res.json()["error"]
    assert body["code"] == "INVALID_REQUEST"
    assert body["issues"][0]["field"] == "parameters.rules.direction"


def test_invalid_inline_strategy_fails_before_backtest_execution():
    res = client.post(
        "/api/v1/backtests",
        json={
            "strategy": {
                "category": "risk_rotation",
                "name": "Invalid Inline Rule",
                "methodology": "Should not execute.",
                "parameters": _rule(instrument="SQQQ", direction="short"),
            },
            "tickers": ["SQQQ"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-05",
            "starting_cash": 10000,
            "use_fixture_data": True,
        },
    )
    assert res.status_code == 400
    body = res.json()["error"]
    assert body["code"] == "INVALID_REQUEST"
    assert any(issue["code"] == "incompatible_family" for issue in body["issues"])
