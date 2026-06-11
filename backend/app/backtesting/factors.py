"""Point-in-time technical factors (PRD backtest-integrity).

Every factor uses only bars dated on or before the evaluation date D, so no future
information can leak into a historical decision. ``bars`` is a list of dicts with
``date`` (ISO string) and ``close``, assumed sorted ascending by date.
"""
from __future__ import annotations

import bisect
from datetime import date


def _iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


# --------------------------------------------------------------------------- #
# Compact-series factors (PRD oom-fix): operate on parallel arrays
# ``dates: list[str]`` (ascending) + ``closes: list[float]`` instead of a fat
# list-of-dicts. ~5–10× less memory, which is what lets a full S&P 500 scan fit
# in a 512MB instance. ``k`` is the count of bars dated on/before the eval date
# (closes[:k] are visible), found once per evaluation via bisect.
# --------------------------------------------------------------------------- #

def idx_asof(dates: list[str], D) -> int:
    """Count of bars with date <= D (so closes[:idx] are the point-in-time visible closes)."""
    return bisect.bisect_right(dates, _iso(D))


def close_at(dates: list[str], closes: list[float], D) -> float | None:
    k = bisect.bisect_right(dates, _iso(D))
    return closes[k - 1] if k > 0 else None


def sma_at(closes: list[float], k: int, n: int) -> float | None:
    if n <= 0 or k < n:
        return None
    return sum(closes[k - n:k]) / n


def momentum_at(closes: list[float], k: int, lookback: int) -> float | None:
    if lookback <= 0 or k <= lookback or closes[k - 1 - lookback] == 0:
        return None
    return closes[k - 1] / closes[k - 1 - lookback] - 1


def momentum_12_1_at(closes: list[float], k: int) -> float | None:
    """Classic cross-sectional momentum (Jegadeesh & Titman): the trailing-12-month
    return *excluding the most recent month*, which mean-reverts and would otherwise
    contaminate the signal."""
    m12 = momentum_at(closes, k, 252)
    m1 = momentum_at(closes, k, 21)
    if m12 is None or m1 is None or (1 + m1) == 0:
        return None
    return (1 + m12) / (1 + m1) - 1


def volatility_at(closes: list[float], k: int, lookback: int) -> float | None:
    """Daily-return standard deviation over the trailing ``lookback`` bars at index k."""
    if lookback <= 1 or k <= lookback:
        return None
    window = closes[k - lookback - 1:k]
    rets = [window[i] / window[i - 1] - 1 for i in range(1, len(window)) if window[i - 1]]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return var ** 0.5


def rsi_at(closes: list[float], k: int, n: int = 14) -> float | None:
    """Cutler's RSI (simple-average form) over the last ``n`` changes at index k."""
    if n <= 0 or k < n + 1:
        return None
    window = closes[k - n - 1:k]
    gains = losses = 0.0
    for i in range(1, len(window)):
        change = window[i] - window[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100.0 - 100.0 / (1.0 + rs)


def high_proximity_at(closes: list[float], k: int, lookback: int = 252) -> float | None:
    """Latest close as a fraction of the trailing ``lookback``-bar high (1.0 = at the high)."""
    if lookback <= 0 or k < lookback:
        return None
    high = max(closes[k - lookback:k])
    return closes[k - 1] / high if high else None


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
