from app.core.http import _redact_url


def test_redact_url_hides_sensitive_query_values():
    redacted = _redact_url(
        "https://financialmodelingprep.com/stable/most-actives?apikey=real-secret&symbol=AAPL&token=abc123"
    )

    assert "real-secret" not in redacted
    assert "abc123" not in redacted
    assert "apikey=REDACTED" in redacted
    assert "token=REDACTED" in redacted
    assert "symbol=AAPL" in redacted
