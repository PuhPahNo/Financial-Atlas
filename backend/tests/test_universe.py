"""S&P 500 universe sourcing (PRD active-sp500-screening)."""
from app.backtesting import universe


def test_parse_csv_normalizes_symbols():
    text = "Symbol,Security,Sector\nAAPL,Apple,Tech\nBRK.B,Berkshire,Fin\n\n"
    assert universe._parse_csv(text) == ["AAPL", "BRK-B"]


def test_falls_back_to_bundled_list_when_fetch_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(universe, "get_text", boom)
    out = universe.sp500_tickers()
    assert len(out) >= 100 and "AAPL" in out  # bundled large-cap fallback, non-empty
