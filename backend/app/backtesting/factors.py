"""Point-in-time technical factors (PRD backtest-integrity).

Every factor uses only bars dated on or before the evaluation date D, so no future
information can leak into a historical decision. ``bars`` is a list of dicts with
``date`` (ISO string) and ``close``, assumed sorted ascending by date.
"""
from __future__ import annotations

from datetime import date


def _iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


def _closes_upto(bars: list[dict], D) -> list[float]:
    cutoff = _iso(D)
    return [float(b["close"]) for b in bars
            if b.get("close") is not None and str(b["date"])[:10] <= cutoff]


def close_on(bars: list[dict], D) -> float | None:
    closes = _closes_upto(bars, D)
    return closes[-1] if closes else None


def sma(bars: list[dict], D, n: int) -> float | None:
    closes = _closes_upto(bars, D)
    if n <= 0 or len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def trend(bars: list[dict], D, n: int) -> float | None:
    """Close relative to its n-day SMA (>0 means above trend)."""
    s = sma(bars, D, n)
    px = close_on(bars, D)
    if s is None or px is None or s == 0:
        return None
    return px / s - 1


def momentum(bars: list[dict], D, lookback: int) -> float | None:
    """Total return over the trailing ``lookback`` trading days."""
    closes = _closes_upto(bars, D)
    if lookback <= 0 or len(closes) <= lookback or closes[-lookback - 1] == 0:
        return None
    return closes[-1] / closes[-lookback - 1] - 1


def pct_change(bars: list[dict], D, window: int) -> float | None:
    return momentum(bars, D, window)


def volatility(bars: list[dict], D, lookback: int) -> float | None:
    closes = _closes_upto(bars, D)
    if len(closes) <= lookback:
        return None
    window = closes[-lookback - 1:]
    rets = [window[i] / window[i - 1] - 1 for i in range(1, len(window)) if window[i - 1]]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return var ** 0.5


def new_high(bars: list[dict], D, channel: int) -> bool | None:
    """True if the latest close (at/<=D) is a new high over the prior ``channel`` days."""
    closes = _closes_upto(bars, D)
    if channel <= 0 or len(closes) < channel + 1:
        return None
    return closes[-1] >= max(closes[-channel - 1:-1])


def relative_strength(bars: list[dict], bench: list[dict], D, lookback: int) -> float | None:
    """Own momentum minus the benchmark's over the same lookback."""
    m = momentum(bars, D, lookback)
    mb = momentum(bench, D, lookback)
    if m is None or mb is None:
        return None
    return m - mb
