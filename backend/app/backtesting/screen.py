"""Active point-in-time screening backtest engine (PRD active-sp500-screening, oom-fix,
backtest-integrity).

Each day, scan the universe and buy names that *newly* meet the model's criteria
(point-in-time — only data available at that date), exit on take-profit / stop-loss /
max-hold / criteria-break, holding at most top-N, equal-weighted.

Integrity contract:
* **Adjusted prices** — all closes are dividend/split-adjusted (via the price store).
* **Next-bar execution** — eligibility is evaluated with data through the *prior* day
  and fills happen at *today's* close, so no decision ever uses the price it fills at.
  Price-triggered exits (take-profit / stop-loss) evaluate and fill on the same close,
  which leaks nothing: the trigger and the fill are one observed price.
* **Point-in-time fundamentals** — originally-filed figures gated by original filing
  dates (see ``pit_fundamentals``).

Memory: prices are held as compact parallel arrays (``dates`` + ``closes``), not a fat
list-of-dicts, so a full S&P 500 scan fits in a 512MB instance. Heavy runs are serialized
by ``_ENGINE_LOCK`` so concurrent requests / the live-mark tick can't stack and OOM the box.

Marking convention (shared with the rule engine and the live mark): a position stores a
positive ``qty`` + ``direction`` + ``entry_price``; long value = qty·price, short value =
qty·(entry − price). Cash is not credited with short proceeds — short P&L flows through the
entry-vs-price term, keeping net liquidation conserved.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

from ..core import cache
from ..core.errors import ValidationError
from ..services import price_store
from . import factors
from .integrity import build_integrity
from .metrics import summarize
from .pit_fundamentals import as_of, as_of_with_prior

_DEFAULT_MAX_POSITIONS = 8

# Serialize heavy backtests process-wide: only one universe scan runs at a time, so
# concurrent backtest requests + the market-open live-mark tick can't stack their memory
# and blow past the instance limit. (Backtests queue rather than crash the whole app.)
_ENGINE_LOCK = threading.Lock()

# Dead-ticker skiplist: symbols whose price fetch hard-errors (404 / unresolved — typically
# delisted names in the historical superset) are remembered so the engine stops re-fetching
# corpses on every backtest. Short TTL so a transient error self-heals.
_DEAD_TTL = 7 * 86400

_UNIVERSE_CAVEAT = ("Candidate universe is user-specified or current-day; survivorship/"
                    "selection bias is not modeled (historical index membership absent).")


def _is_dead(ticker: str) -> bool:
    return cache.peek("dead_ticker", ticker.upper(), _DEAD_TTL) is True


def _mark_dead(ticker: str) -> None:
    cache.put("dead_ticker", ticker.upper(), True)


def _leg_value(pos: dict, price: float) -> float:
    if pos["direction"] == "short":
        return pos["qty"] * (pos["entry_price"] - price)
    return pos["qty"] * price


def _max_positions(category: str, params: dict) -> int:
    if category == "risk_rotation":
        # Rotation holds the single strongest name (or cash) unless the model explicitly
        # asks for breadth (e.g. Faber GTAA holds every asset class above its trend line).
        try:
            return max(1, int(params.get("max_positions") or 1))
        except (TypeError, ValueError):
            return 1
    try:
        return max(1, int(params.get("max_positions") or _DEFAULT_MAX_POSITIONS))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_POSITIONS


def _pct(value, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    return v / 100 if v > 1 else v


def _num(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _load_series(sym: str, warmup_start: date, end_date: date) -> tuple[list[str], list[float]]:
    """A ticker's daily history as compact ascending (dates, adjusted closes) arrays,
    served from the durable price store (network only for never-seen bars)."""
    dates, closes, _ = price_store.get_series(sym, warmup_start, end_date)
    return dates, closes


# --------------------------------------------------------------------------- #
# Mainstream model library (PRD model-lab)                                    #
#                                                                              #
# Each model maps (params, ticker, d, dates, closes, k, px) -> (ok, score,    #
# direction). ``d`` is the signal date (data through d only), ``k`` the count #
# of visible bars, ``px`` the latest visible close. The engine ranks eligible #
# names by score and equal-weights the top N.                                 #
# --------------------------------------------------------------------------- #

def piotroski_f_score(cur: dict | None, prev: dict | None) -> int | None:
    """Piotroski (2000) F-Score, 0–9, from two consecutive annual PIT rows.
    Requires the prior year — without it five of the nine signals are undefined."""
    if not cur or not prev:
        return None
    ni, ta = cur.get("net_income"), cur.get("total_assets")
    ni_p, ta_p = prev.get("net_income"), prev.get("total_assets")
    cfo = cur.get("operating_cash_flow")
    if ni is None or not ta or cfo is None:
        return None
    score = 0
    roa = ni / ta
    roa_p = (ni_p / ta_p) if (ni_p is not None and ta_p) else None
    # Profitability
    score += 1 if roa > 0 else 0
    score += 1 if cfo > 0 else 0
    score += 1 if (roa_p is not None and roa > roa_p) else 0
    score += 1 if cfo > ni else 0  # accruals: cash earnings back the accounting earnings
    # Leverage, liquidity, dilution
    ltd, ltd_p = cur.get("long_term_debt"), prev.get("long_term_debt")
    if ltd is not None and ltd_p is not None and ta and ta_p:
        score += 1 if (ltd / ta) <= (ltd_p / ta_p) else 0
    tca, tcl = cur.get("total_current_assets"), cur.get("total_current_liabilities")
    tca_p, tcl_p = prev.get("total_current_assets"), prev.get("total_current_liabilities")
    if tca and tcl and tca_p and tcl_p:
        score += 1 if (tca / tcl) > (tca_p / tcl_p) else 0
    sh, sh_p = cur.get("shares"), prev.get("shares")
    if sh and sh_p:
        score += 1 if sh <= sh_p * 1.02 else 0  # ≤2% drift ≈ no meaningful issuance
    # Operating efficiency
    gp, gp_p = cur.get("gross_profit"), prev.get("gross_profit")
    rev, rev_p = cur.get("revenue"), prev.get("revenue")
    if gp is not None and rev and gp_p is not None and rev_p:
        score += 1 if (gp / rev) > (gp_p / rev_p) else 0
    if rev and ta and rev_p and ta_p:
        score += 1 if (rev / ta) > (rev_p / ta_p) else 0
    return score


def _m_f_score(params, ticker, d, dates, closes, k, px):
    cur, prev = as_of_with_prior(ticker, d)
    score = piotroski_f_score(cur, prev)
    if score is None:
        return (False, 0.0, "long")
    min_score = int(_num(params.get("min_f_score"), 7))
    shares = (cur or {}).get("shares")
    fcf_yield = ((cur or {}).get("fcf") or 0.0) / (shares * px) if (shares and shares > 0) else 0.0
    return (score >= min_score, score + max(fcf_yield, 0.0), "long")


def _m_magic_formula(params, ticker, d, dates, closes, k, px):
    f = as_of(ticker, d)
    if not f:
        return (False, 0.0, "long")
    ebit, shares, net_debt = f.get("operating_income"), f.get("shares"), f.get("net_debt")
    ta, tcl = f.get("total_assets"), f.get("total_current_liabilities")
    if not ebit or ebit <= 0 or not shares or shares <= 0:
        return (False, 0.0, "long")
    ev = shares * px + (net_debt or 0.0)
    capital = (ta or 0.0) - (tcl or 0.0)
    if ev <= 0 or capital <= 0:
        return (False, 0.0, "long")
    earnings_yield = ebit / ev
    roc = ebit / capital
    ok = earnings_yield >= _num(params.get("min_earnings_yield"), 0.04) and roc >= _num(params.get("min_roc"), 0.10)
    # Greenblatt ranks the two factors; their sum is a rank-free proxy with the same spirit.
    return (ok, earnings_yield + roc, "long")


def _m_value_composite(params, ticker, d, dates, closes, k, px):
    f = as_of(ticker, d)
    if not f:
        return (False, 0.0, "long")
    shares = f.get("shares")
    if not shares or shares <= 0:
        return (False, 0.0, "long")
    mktcap = shares * px
    fcf_yield = (f.get("fcf") or 0.0) / mktcap
    earnings_yield = (f.get("net_income") or 0.0) / mktcap
    ok = fcf_yield > 0 and earnings_yield > 0
    return (ok, (fcf_yield + earnings_yield) / 2, "long")


def _m_momentum_12_1(params, ticker, d, dates, closes, k, px):
    mom = factors.momentum_12_1_at(closes, k)
    if mom is None:
        return (False, 0.0, "long")
    return (mom > 0, mom, "long")


def _m_high_52w(params, ticker, d, dates, closes, k, px):
    prox = factors.high_proximity_at(closes, k, 252)
    if prox is None:
        return (False, 0.0, "long")
    return (prox >= _num(params.get("min_proximity"), 0.95), prox, "long")


def _m_low_volatility(params, ticker, d, dates, closes, k, px):
    vol = factors.volatility_at(closes, k, 252)
    if vol is None:
        return (False, 0.0, "long")
    annualized = vol * (252 ** 0.5)
    ok = annualized <= _num(params.get("max_volatility"), 0.25)
    return (ok, -annualized, "long")  # calmer names rank higher


def _m_rsi_reversion(params, ticker, d, dates, closes, k, px):
    rsi = factors.rsi_at(closes, k, int(_num(params.get("rsi_days"), 2)))
    sma200 = factors.sma_at(closes, k, 200)
    if rsi is None or sma200 is None:
        return (False, 0.0, "long")
    # Connors: buy deep short-term oversold *within* a long-term uptrend.
    ok = px > sma200 and rsi <= _num(params.get("max_rsi"), 10.0)
    return (ok, -rsi, "long")


def _m_dividend_yield(params, ticker, d, dates, closes, k, px):
    f = as_of(ticker, d)
    if not f or not f.get("fcf"):
        return (False, 0.0, "long")
    shares = f.get("shares")
    dividends = f.get("dividends_paid") or 0.0
    if not shares or shares <= 0 or dividends <= 0:
        return (False, 0.0, "long")
    div_yield = dividends / (shares * px)
    covered = f["fcf"] >= dividends * _num(params.get("min_fcf_coverage"), 1.0)
    return (covered and div_yield >= _num(params.get("min_yield"), 0.03), div_yield, "long")


def _m_dual_momentum(params, ticker, d, dates, closes, k, px):
    look = int(_num(params.get("lookback_days"), 252))
    mom = factors.momentum_at(closes, k, look)
    if mom is None:
        return (False, 0.0, "long")
    # Absolute momentum gates entry; relative momentum is the ranking (engine keeps top-1
    # for risk_rotation). Negative everywhere → the model stays in cash.
    return (mom > 0, mom, "long")


def _m_trend_following(params, ticker, d, dates, closes, k, px):
    sma = factors.sma_at(closes, k, int(_num(params.get("sma_days"), 210)))  # ≈ Faber's 10-month SMA
    if sma is None:
        return (False, 0.0, "long")
    mom = factors.momentum_at(closes, k, 126) or 0.0
    return (px > sma, mom, "long")


MODELS = {
    "f_score": _m_f_score,
    "magic_formula": _m_magic_formula,
    "value_composite": _m_value_composite,
    "momentum_12_1": _m_momentum_12_1,
    "high_52w": _m_high_52w,
    "low_volatility": _m_low_volatility,
    "rsi_reversion": _m_rsi_reversion,
    "dividend_yield": _m_dividend_yield,
    "dual_momentum": _m_dual_momentum,
    "trend_following": _m_trend_following,
}

# Models/categories that read PIT fundamentals (drives the integrity report).
_FUNDAMENTAL_MODELS = {"f_score", "magic_formula", "value_composite", "dividend_yield"}
_FUNDAMENTAL_CATEGORIES = {"long_term", "income_quality"}


def uses_fundamentals(category: str, params: dict) -> bool:
    model = str((params or {}).get("model") or "").strip().lower()
    if model:
        return model in _FUNDAMENTAL_MODELS
    return category in _FUNDAMENTAL_CATEGORIES


def eligible(category: str, params: dict, ticker: str, d, dates: list[str], closes: list[float]):
    """Point-in-time eligibility for one candidate at date d → (ok, score, direction).
    Uses only closes dated on/before d (and, for fundamental models, filings filed by d)."""
    k = factors.idx_asof(dates, d)
    if k == 0:
        return (False, 0.0, "long")
    px = closes[k - 1]
    if px <= 0:
        return (False, 0.0, "long")

    # Named mainstream models take precedence over the category defaults.
    model = str((params or {}).get("model") or "").strip().lower()
    fn = MODELS.get(model)
    if fn is not None:
        return fn(params, ticker, d, dates, closes, k, px)

    if category == "long_term":
        f = as_of(ticker, d)
        if not f or not f.get("fcf"):
            return (False, 0.0, "long")
        max_dtf = float(params.get("max_debt_to_fcf") or 6.0)
        ndf = f.get("net_debt_to_fcf")
        ok = (f["fcf"] > 0 and (f.get("fcf_margin") or 0.0) >= 0.05
              and (ndf is None or ndf <= max_dtf))
        shares = f.get("shares")
        fcf_yield = (f["fcf"] / (shares * px)) if (shares and shares > 0) else 0.0
        return (ok, fcf_yield, "long")

    if category == "income_quality":
        f = as_of(ticker, d)
        if not f or not f.get("fcf"):
            return (False, 0.0, "long")
        shares = f.get("shares")
        dividends = f.get("dividends_paid") or 0.0
        div_yield = (dividends / (shares * px)) if (shares and shares > 0) else 0.0
        min_yield = float(params.get("min_yield") or 0.02)
        min_cov = float(params.get("min_fcf_coverage") or 1.5)
        covered = dividends > 0 and f["fcf"] >= dividends * min_cov
        return (covered and div_yield >= min_yield, div_yield, "long")

    if category == "options":  # synthetic proxy → point-in-time trend filter on the underlying
        sma200 = factors.sma_at(closes, k, 200)
        t = (px / sma200 - 1) if sma200 else None
        return (t is not None and t > 0, t or 0.0, "long")

    if category == "short_selling":
        slow = int(params.get("slow_days") or 100)
        sma = factors.sma_at(closes, k, slow)
        mom = factors.momentum_at(closes, k, 120)
        if sma is None or mom is None:
            return (False, 0.0, "short")
        return (px < sma and mom < 0, -mom, "short")

    if category == "risk_rotation":
        look = int(params.get("lookback_days") or 126)
        mom = factors.momentum_at(closes, k, look)
        sma200 = factors.sma_at(closes, k, 200)
        if mom is None or sma200 is None:
            return (False, 0.0, "long")
        return (px > sma200 and mom > 0, mom, "long")

    # short_term and any unmapped category → trend + momentum gate
    slow = int(params.get("slow_days") or 100)
    sma = factors.sma_at(closes, k, slow)
    mom = factors.momentum_at(closes, k, 120)
    if sma is None or mom is None:
        return (False, 0.0, "long")
    return (px > sma and mom > 0, mom, "long")


def warm_universe_for_backtests(universe: list[str] | None = None, *, end_date: date | None = None,
                                years: int = 5, include_fundamentals: bool = True) -> dict:
    """Best-effort pre-fetch of the universe's price history into the durable store
    (and, optionally, fundamentals into the PIT table) so backtests read locally instead
    of issuing hundreds of cold provider calls. Never raises."""
    from .universe import sp500_tickers
    universe = universe or sp500_tickers()
    end_date = end_date or date.today()
    warmup_start = date(max(1962, end_date.year - years), 1, 1)
    prices_ok = funds_ok = 0
    for t in universe:
        if _is_dead(t):
            continue
        if price_store.warm(t, warmup_start, end_date):
            prices_ok += 1
        else:
            _mark_dead(t)
            continue
        if include_fundamentals:
            try:
                if as_of(t, end_date) is not None:
                    funds_ok += 1
            except Exception:  # noqa: BLE001
                pass
    return {"universe": len(universe), "prices_warmed": prices_ok, "fundamentals_warmed": funds_ok}


def run_active_backtest(*, strategy: dict, universe: list[str], start_date: date, end_date: date,
                        starting_cash: float, transaction_cost_bps: float = 5.0,
                        slippage_bps: float = 5.0, benchmark: str = "SPY", membership_on=None,
                        universe_kind: str = "index") -> dict:
    """Actively manage the universe: each day, close positions that hit a take-profit /
    stop-loss / max-hold / criteria-break, then fill free slots with the best names that
    *newly* meet the model's criteria. Eligibility is computed with data through the
    *prior* session and fills execute at *today's* close (next-bar execution). Serialized
    via ``_ENGINE_LOCK`` and memory-lean (compact price arrays)."""
    if end_date <= start_date:
        raise ValidationError("Backtest end_date must be after start_date")
    category = strategy.get("category") or "short_term"
    params = strategy.get("parameters", {}) or {}
    universe = sorted({t.strip().upper() for t in (universe or []) if t and t.strip()})
    if not universe:
        raise ValidationError("Active screening needs a non-empty universe")

    cost_rate = (transaction_cost_bps + slippage_bps) / 10000
    top_n = _max_positions(category, params)
    if category != "risk_rotation":
        try:
            top_n = max(1, int(params.get("max_positions") or 15))
        except (TypeError, ValueError):
            top_n = 15
    take_profit = _pct(params.get("take_profit_pct") or params.get("take_profit"), 0.25)
    stop_loss = _pct(params.get("stop_loss_pct") or params.get("stop_loss"), 0.12)
    max_hold = int(params.get("max_hold_days") or 252)
    warnings: list[str] = []
    if membership_on is None and universe_kind == "index":
        warnings.append(_UNIVERSE_CAVEAT)
    warmup_start = date(max(1962, start_date.year - 2), 1, 1)

    # Only one heavy universe scan at a time — prevents concurrent requests / the live-mark
    # tick from stacking memory and OOM-killing the instance.
    with _ENGINE_LOCK:
        series: dict[str, tuple[list[str], list[float]]] = {}
        for t in universe:
            if _is_dead(t):
                continue  # known no-data symbol — don't re-fetch corpses
            try:
                dates, closes = _load_series(t, warmup_start, end_date)
                if closes:
                    series[t] = (dates, closes)
            except Exception:  # noqa: BLE001 — symbol won't resolve (often delisted) → skiplist it
                _mark_dead(t)
                continue
        if not series:
            raise ValidationError("No price history available for the universe in this window")

        bench_dates: list[str] = []
        bench_closes: list[float] = []
        if benchmark:
            try:
                bench_dates, bench_closes = _load_series(benchmark, warmup_start, end_date)
            except Exception:  # noqa: BLE001
                warnings.append(f"Benchmark {benchmark.upper()} history was unavailable for this window.")

        s_iso, e_iso = start_date.isoformat(), end_date.isoformat()
        cal_set = {ds for (dates, _) in series.values() for ds in dates if s_iso <= ds <= e_iso}
        calendar = [date.fromisoformat(ds) for ds in sorted(cal_set)]
        if len(calendar) < 2:
            raise ValidationError("Not enough trading days in the window")
        bench_first = factors.close_at(bench_dates, bench_closes, calendar[0]) if bench_closes else None

        def close(sym: str, d):
            ds, cs = series[sym]
            return factors.close_at(ds, cs, d)

        cash = float(starting_cash)
        positions: dict[str, dict] = {}
        trades: list[dict] = []
        equity_curve: list[dict] = []

        def mark_equity(d) -> float:
            return cash + sum(_leg_value(p, (close(t, d) or p["entry_price"])) for t, p in positions.items())

        for d in calendar:
            # Signal cutoff: decisions made *today* may only see data through *yesterday*.
            # (Take-profit/stop-loss are price-triggered: the trigger and the fill are the
            # same observed close, so they evaluate on today's price without leaking.)
            sig = d - timedelta(days=1)

            # 1) Exits — take-profit / stop-loss / max-hold / criteria-break, whichever first.
            for t in list(positions):
                p = positions[t]
                px = close(t, d)
                if px is None:
                    continue
                gain = (px / p["entry_price"] - 1) if p["direction"] == "long" else (p["entry_price"] / px - 1)
                held = (d - p["entry_date"]).days
                reason = None
                if gain >= take_profit:
                    reason = f"take-profit +{take_profit * 100:.0f}%"
                elif gain <= -stop_loss:
                    reason = f"stop-loss -{stop_loss * 100:.0f}%"
                elif held >= max_hold:
                    reason = f"max-hold {max_hold}d"
                else:
                    ok, _, _ = eligible(category, params, t, sig, *series[t])
                    if not ok:
                        reason = "criteria exit"
                if reason:
                    pnl = (p["qty"] * (px - p["entry_price"]) if p["direction"] == "long"
                           else p["qty"] * (p["entry_price"] - px))
                    cash += pnl if p["direction"] == "short" else p["qty"] * px
                    cash -= p["qty"] * px * cost_rate
                    trades.append({"date": d, "ticker": t, "side": "cover" if p["direction"] == "short" else "sell",
                                   "quantity": p["qty"], "price": px, "value": abs(p["qty"] * px),
                                   "reason": reason, "pnl": pnl})
                    del positions[t]

            # 2) Entries — fill free slots with the best names that qualified as of
            #    yesterday's data, paying today's close (next-bar execution).
            if len(positions) < top_n:
                equity_now = mark_equity(d)
                target = max(0.0, equity_now) / top_n
                members = membership_on(d) if membership_on is not None else None
                cands = []
                for t, (dates, closes) in series.items():
                    if t in positions:
                        continue
                    if members is not None and t not in members:
                        continue  # not in the index on this date (point-in-time membership)
                    ok, score, direction = eligible(category, params, t, sig, dates, closes)
                    if not ok:
                        continue
                    fill_px = close(t, d)
                    if fill_px is None or fill_px <= 0:
                        continue  # no tradable bar today — no fill
                    cands.append((score, t, direction, fill_px))
                cands.sort(key=lambda x: x[0], reverse=True)
                for score, t, direction, px in cands:
                    if len(positions) >= top_n:
                        break
                    dollars = target if direction == "short" else min(target, cash)
                    if dollars <= 1 or px <= 0:
                        continue
                    qty = dollars / px
                    cash -= dollars if direction == "long" else 0.0
                    cash -= dollars * cost_rate
                    positions[t] = {"qty": qty, "direction": direction, "entry_price": px, "entry_date": d}
                    trades.append({"date": d, "ticker": t, "side": "short" if direction == "short" else "buy",
                                   "quantity": qty, "price": px, "value": dollars, "reason": "criteria met"})

            # 3) Mark net liquidation.
            eq = mark_equity(d)
            point = {"date": d, "cash": cash, "equity": eq}
            if bench_first:
                bclose = factors.close_at(bench_dates, bench_closes, d)
                point["benchmark_equity"] = starting_cash * ((bclose or bench_first) / bench_first)
            equity_curve.append(point)

        last_day = calendar[-1]
        final_holdings = [{
            "ticker": t, "quantity": p["qty"], "direction": p["direction"],
            "entry_price": p["entry_price"], "last_close": (close(t, last_day) or p["entry_price"]),
        } for t, p in positions.items()]
        final_equity = equity_curve[-1]["equity"] if equity_curve else starting_cash
        holdings = [{"ticker": t, "weight": round(abs(_leg_value(p, (close(t, last_day) or p["entry_price"]))) / final_equity, 4)}
                    for t, p in positions.items() if final_equity] or [{"ticker": "Cash", "weight": 1.0}]
        if not trades:
            warnings.append("No candidate met the model's criteria in this window — the model stayed in cash.")

        return {
            "strategy": strategy,
            "served_by": "store",
            "trades": trades,
            "equity_curve": equity_curve,
            "metrics": summarize(equity_curve, trades, starting_cash),
            "warnings": warnings,
            "holdings": holdings,
            "final_holdings": final_holdings,
            "residual_cash": cash,
            "date_range": {"start": start_date, "end": end_date},
            "integrity": build_integrity(
                mode="active_screen",
                uses_fundamentals=uses_fundamentals(category, params),
                membership_pit=(None if universe_kind == "fixed"
                                else membership_on is not None),
                transaction_cost_bps=transaction_cost_bps,
                slippage_bps=slippage_bps,
            ),
        }
