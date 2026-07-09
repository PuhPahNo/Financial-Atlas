"""Seeded paper-trading categories and starter strategies.

Truth-pass invariants (see .scratch/paper-trading-audit/AUDIT.md R1/R2):
- Every parameter listed here is actually read by the engine for that
  category/model. No decorative knobs the backtester ignores.
- No pre-claimed performance numbers: ``metrics`` ships empty, and the
  nightly headline refresh fills real backtested figures.
- Descriptions/methodology state what the engine actually executes. Where a
  theme can't be modeled on daily closes (options premium, channel breakouts),
  the text says so instead of implying math that doesn't run.
"""
from __future__ import annotations

COMMON_CAVEATS = [
    "Research simulation only; not financial advice.",
    "Uses end-of-day data, so fills are approximate.",
]

_NO_SEEDED_METRICS = "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."

CATEGORIES = [
    {"id": "long_term", "label": "Long Term", "description": "Multi-year compounding and valuation discipline."},
    {"id": "short_term", "label": "Short Term", "description": "Trend and volatility signals over shorter windows."},
    {"id": "short_selling", "label": "Short Selling", "description": "Risk-capped bearish hypotheses with strict exits."},
    {"id": "options", "label": "Options", "description": "Synthetic options-themed models using underlying prices."},
    {"id": "income_quality", "label": "Income & Quality", "description": "Durability, cash coverage, and balance-sheet strength."},
    {"id": "risk_rotation", "label": "Risk Rotation", "description": "Relative strength, drawdown control, and cash fallback."},
]

SEED_STRATEGIES = [
    {
        "category": "long_term",
        "name": "FCF Compounder",
        "description": "A fixed basket of durable free-cash-flow generators, gated on FCF quality and leverage.",
        "history": "Inspired by quality and owner-earnings screens used by long-horizon analysts.",
        "methodology": "Within the declared basket, a name is held while its originally-filed free cash flow is "
                       "positive, FCF margin is at least 5%, and net-debt-to-FCF stays under the cap; ranked by "
                       "point-in-time FCF yield.",
        "parameters": {"tickers": ["AAPL", "MSFT", "GOOGL"], "universe": "tickers", "max_debt_to_fcf": 6,
                       "max_positions": 3, "take_profit_pct": 0.50, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "long_term",
        "name": "Margin of Safety Basket",
        "description": "A leverage-strict free-cash-flow basket of large, defensible franchises.",
        "history": "Based on value-investing discipline around downside protection.",
        "methodology": "The same point-in-time FCF-quality gate as the compounder screen but with a tighter "
                       "net-debt-to-FCF ceiling, so only the least-levered names qualify; ranked by FCF yield.",
        "parameters": {"tickers": ["BRK-B", "JPM", "HD"], "universe": "tickers", "max_debt_to_fcf": 3,
                       "max_positions": 3, "take_profit_pct": 0.50, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "long_term",
        "name": "Owner Earnings Quality",
        "description": "Low-leverage compounders held on free-cash-flow durability.",
        "history": "Uses the Atlas owner-earnings vocabulary from valuation research.",
        "methodology": "Point-in-time FCF-quality gate (positive free cash flow, FCF margin ≥ 5%) with a moderate "
                       "net-debt-to-FCF cap; ranked by FCF yield.",
        "parameters": {"tickers": ["COST", "V", "MA"], "universe": "tickers", "max_debt_to_fcf": 4,
                       "max_positions": 3, "take_profit_pct": 0.50, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "short_term",
        "name": "Dual Momentum",
        "description": "Rides the strongest names in a growth basket while they trend above their medium-term average.",
        "history": "Relative-strength trend following adapted to Atlas price providers.",
        "methodology": "A name is held while its close is above its ~80-day moving average and its 12-month momentum "
                       "is positive; ranked by momentum. (Distinct from the GEM asset-class model in Risk Rotation.)",
        "parameters": {"tickers": ["NVDA", "AMD", "AVGO"], "universe": "tickers", "slow_days": 80,
                       "max_positions": 3, "take_profit_pct": 0.30, "stop_loss_pct": 0.15, "max_hold_days": 90},
        "metrics": {},
    },
    {
        "category": "short_term",
        "name": "Volatility Breakout",
        "description": "Holds broad ETFs while they trend above their medium-term average with positive momentum.",
        "history": "A daily-bar trend filter — true intraday range-expansion breakouts can't be modeled on "
                   "end-of-day data.",
        "methodology": "Approximated with a trend gate: hold while the close is above its ~55-day moving average and "
                       "12-month momentum is positive. Channel/volatility-compression breakout logic is not modeled "
                       "on daily closes.",
        "parameters": {"tickers": ["SPY", "QQQ", "IWM"], "universe": "tickers", "slow_days": 55,
                       "max_positions": 3, "take_profit_pct": 0.20, "stop_loss_pct": 0.10, "max_hold_days": 60},
        "metrics": {},
    },
    {
        "category": "short_term",
        "name": "Mean Reversion Guardrail",
        "description": "Buys deep short-term oversold dips in broad ETFs that remain in long-term uptrends.",
        "history": "A Larry Connors-style RSI(2) reversal with strict risk bands.",
        "methodology": "Eligible when the 2-day RSI falls to 10 or below while price holds above its 200-day "
                       "average; exits when the oversold reading clears (criteria exit) or on tight profit/stop bands.",
        "parameters": {"tickers": ["SPY", "DIA", "QQQ"], "universe": "tickers", "model": "rsi_reversion",
                       "rsi_days": 2, "max_rsi": 10, "max_positions": 3,
                       "take_profit_pct": 0.05, "stop_loss_pct": 0.05, "max_hold_days": 10},
        "metrics": {},
    },
    {
        "category": "short_term",
        "name": "Momentum Cross (QQQ)",
        "description": "Buys QQQ when its 20-day average crosses above the 50-day, exits on a quick profit or stop.",
        "history": "A textbook moving-average crossover, expressed as a signal rule the engine can backtest.",
        "methodology": "Signal: 20-day SMA crosses above 50-day SMA on QQQ. Enter long QQQ, take profit at +8%, stop at -4%.",
        "parameters": {
            "tickers": ["QQQ"],
            "rules": {
                "instrument": "QQQ",
                "direction": "long",
                "signal": {"type": "ma_cross_up", "reference": "QQQ", "fast_days": 20, "slow_days": 50},
                "take_profit_pct": 0.08,
                "stop_loss_pct": 0.04,
                "max_hold_days": 60,
            },
        },
        "metrics": {},
    },
    {
        "category": "short_selling",
        "name": "Weak FCF Short",
        "description": "Shorts weak-trending, high-controversy names with a hard stop.",
        "history": "Pairs technical weakness with a capped-risk exit.",
        "methodology": "Within the declared basket, shorts a name while its close is below its ~100-day average and "
                       "its 12-month momentum is negative; covers on the stop, a profitable decline, or max-hold.",
        "parameters": {"tickers": ["GME", "AMC", "CVNA"], "universe": "tickers", "slow_days": 100,
                       "stop_loss_pct": 0.12, "take_profit_pct": 0.25, "max_positions": 3, "max_hold_days": 60},
        "metrics": {},
    },
    {
        "category": "short_selling",
        "name": "Balance Sheet Stress",
        "description": "Shorts cyclicals with negative price trend, sized for crisis-window stress tests.",
        "history": "Built to probe drawdown behavior in 2008-style regimes.",
        "methodology": "Shorts a basket name while its close is below its ~100-day average with negative momentum; "
                       "covers on the stop, a profitable decline, or max-hold.",
        "parameters": {"tickers": ["F", "GM", "AAL"], "universe": "tickers", "slow_days": 100,
                       "stop_loss_pct": 0.12, "take_profit_pct": 0.25, "max_positions": 3, "max_hold_days": 60},
        "metrics": {},
    },
    {
        "category": "short_selling",
        "name": "Failed Breakout Short",
        "description": "Shorts high-beta names once their trend rolls over, with a tight stop.",
        "history": "Assumes failed strength in speculative names often unwinds quickly.",
        "methodology": "Shorts a basket name while its close is below its ~100-day average with negative momentum "
                       "and a tight stop. (Intraday breakout-failure detection is not modeled on daily closes.)",
        "parameters": {"tickers": ["TSLA", "COIN", "RIVN"], "universe": "tickers", "slow_days": 100,
                       "stop_loss_pct": 0.08, "take_profit_pct": 0.20, "max_positions": 3, "max_hold_days": 45},
        "metrics": {},
    },
    {
        "category": "options",
        "name": "Synthetic Covered Call",
        "description": "Holds the underlying while it trends above its long-term average — an equity proxy for a "
                       "covered-call sleeve.",
        "history": "Options-themed placeholder until historical options chains are available.",
        "methodology": "Holds each declared underlying while its close is above its 200-day average, long only. "
                       "Option premium income and the capped upside of an actual covered call are NOT modeled — "
                       "this is the underlying's trend exposure only.",
        "parameters": {"tickers": ["AAPL", "MSFT"], "universe": "tickers", "max_positions": 2,
                       "take_profit_pct": 0.25, "stop_loss_pct": 0.12, "max_hold_days": 120},
        "metrics": {},
    },
    {
        "category": "options",
        "name": "Protective Put Proxy",
        "description": "Holds the underlying while it trends above its long-term average — an equity proxy for a "
                       "hedged sleeve.",
        "history": "Synthetic hedge placeholder for scenario analysis without options-chain data.",
        "methodology": "Holds the underlying while its close is above its 200-day average, long only. Put premium "
                       "cost and the drawdown floor of an actual protective put are NOT modeled.",
        "parameters": {"tickers": ["SPY"], "universe": "tickers", "max_positions": 1,
                       "take_profit_pct": 0.25, "stop_loss_pct": 0.12, "max_hold_days": 120},
        "metrics": {},
    },
    {
        "category": "options",
        "name": "Volatility Premium Proxy",
        "description": "Holds broad ETFs while they trend above their long-term average — an equity proxy for a "
                       "short-volatility sleeve.",
        "history": "Placeholder for volatility-premium research on broad ETFs.",
        "methodology": "Holds each ETF while its close is above its 200-day average, long only. Synthetic option "
                       "premium and volatility-regime throttles are NOT modeled.",
        "parameters": {"tickers": ["SPY", "QQQ"], "universe": "tickers", "max_positions": 2,
                       "take_profit_pct": 0.25, "stop_loss_pct": 0.12, "max_hold_days": 120},
        "metrics": {},
    },
    {
        "category": "income_quality",
        "name": "Dividend Coverage",
        "description": "Favors dividends covered by free cash flow.",
        "history": "Income model that avoids yield traps using Atlas FCF analysis.",
        "methodology": "Within the basket, a name qualifies when its point-in-time dividend yield clears the floor "
                       "and free cash flow covers the payout by the required multiple; ranked by yield.",
        "parameters": {"tickers": ["JNJ", "PG", "KO"], "universe": "tickers", "min_yield": 0.02,
                       "min_fcf_coverage": 1.5, "max_positions": 3,
                       "take_profit_pct": 0.40, "stop_loss_pct": 0.18, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "income_quality",
        "name": "Quality Low Vol",
        "description": "Holds the calmest names in the index — the low-volatility anomaly in its plainest form.",
        "history": "Low-volatility portfolios (Haugen & Baker; S&P 500 Low Volatility Index) have historically "
                   "matched the market with smaller drawdowns, defying textbook risk-return intuition.",
        "methodology": "Rank by trailing one-year realized volatility (annualized) and hold the calmest names "
                       "under the volatility ceiling, equal-weight.",
        "parameters": {"tickers": ["PEP", "WMT", "MCD"], "model": "low_volatility", "max_volatility": 0.25,
                       "max_positions": 15, "take_profit_pct": 0.40, "stop_loss_pct": 0.15, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "income_quality",
        "name": "Capital Returns",
        "description": "Favors covered dividend yield backed by strong free cash flow.",
        "history": "Tracks companies returning capital while comfortably covering the payout.",
        "methodology": "Within the basket, a name qualifies when its point-in-time dividend yield clears the floor "
                       "and free cash flow covers the payout by the (higher) required multiple; ranked by yield.",
        "parameters": {"tickers": ["XOM", "CVX", "AAPL"], "universe": "tickers", "min_yield": 0.015,
                       "min_fcf_coverage": 2.0, "max_positions": 3,
                       "take_profit_pct": 0.40, "stop_loss_pct": 0.18, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "risk_rotation",
        "name": "ETF Relative Strength",
        "description": "Rotates into the strongest ETF while it's trending, else falls back to cash.",
        "history": "A simple tactical allocation model for regime shifts.",
        "methodology": "Each day, ranks the basket by trailing momentum and holds the single strongest ETF while it "
                       "is above its 200-day average with positive momentum; when none qualifies, it sits in cash.",
        "parameters": {"tickers": ["SPY", "QQQ", "TLT", "GLD"], "universe": "tickers", "lookback_days": 126,
                       "max_positions": 1, "take_profit_pct": 0.99, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "risk_rotation",
        "name": "Drawdown Brake",
        "description": "Holds equities only while they trend, stepping to cash when the trend breaks.",
        "history": "A risk-first overlay for equity exposure.",
        "methodology": "Holds SPY while its close is above its 200-day average with positive momentum; otherwise "
                       "rotates to cash. The trend break is the brake.",
        "parameters": {"tickers": ["SPY"], "universe": "tickers", "lookback_days": 126,
                       "max_positions": 1, "take_profit_pct": 0.99, "stop_loss_pct": 0.10, "max_hold_days": 365},
        "metrics": {},
    },
    {
        "category": "risk_rotation",
        "name": "S&P High Fade (SQQQ)",
        "description": "When the S&P 500 prints a new all-time high, buys the inverse Nasdaq ETF SQQQ and exits on a 10% gain or a 3% stop.",
        "history": "A contrarian hedge: it assumes froth at fresh index highs and takes a small, tightly-stopped bet on a pullback.",
        "methodology": "Signal: ^GSPC closes at a new all-time high. Enter long SQQQ (a -3x Nasdaq ETF), take profit at +10%, stop loss at -3%, time-stop after 30 days.",
        "parameters": {
            "tickers": ["SQQQ"],
            "rules": {
                "instrument": "SQQQ",
                "direction": "long",
                "signal": {"type": "new_high", "reference": "^GSPC"},
                "take_profit_pct": 0.10,
                "stop_loss_pct": 0.03,
                "max_hold_days": 30,
            },
        },
        "caveats": [
            "Research simulation only; not financial advice.",
            "Inverse/leveraged ETFs decay over time — short holding periods only.",
            "SQQQ began trading in 2010, so pre-2010 windows have no fills.",
        ],
        "metrics": {},
    },
    {
        "category": "risk_rotation",
        "name": "Crisis Rotation",
        "description": "Rotates into whichever of stocks, bonds, or gold is trending, else cash.",
        "history": "Designed for stress windows like 2006-2009 where drawdown control matters.",
        "methodology": "Each day, ranks SPY, TLT and GLD by trailing momentum and holds the single strongest while "
                       "it is above its 200-day average with positive momentum; when none qualifies, it sits in cash.",
        "parameters": {"tickers": ["SPY", "TLT", "GLD"], "universe": "tickers", "lookback_days": 126,
                       "max_positions": 1, "take_profit_pct": 0.99, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
    },
    # ------------------------------------------------------------------ #
    # Mainstream academic / practitioner models (PRD model-lab).          #
    # Metrics ship empty on purpose: every number shown comes from a real #
    # point-in-time backtest run in this workspace, never a seeded claim. #
    # ------------------------------------------------------------------ #
    {
        "category": "long_term",
        "name": "Piotroski F-Score",
        "description": "Buys financially strengthening companies scoring 7+ on Piotroski's nine accounting signals.",
        "history": "Joseph Piotroski (2000), 'Value Investing: The Use of Historical Financial Statement "
                   "Information to Separate Winners from Losers' — one of the most replicated quality screens in finance.",
        "methodology": "Each year of originally-filed 10-K data is scored on nine signals: positive ROA and "
                       "operating cash flow, improving ROA, cash flow above net income (low accruals), falling "
                       "leverage, improving current ratio, no share issuance, improving gross margin, and improving "
                       "asset turnover. Names scoring at least the minimum (default 7) qualify; ranked by score "
                       "plus free-cash-flow yield.",
        "parameters": {"tickers": [], "model": "f_score", "min_f_score": 7, "max_positions": 12,
                       "take_profit_pct": 0.50, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "long_term",
        "name": "Magic Formula",
        "description": "Joel Greenblatt's two-factor screen: cheap (earnings yield) and good (return on capital).",
        "history": "Popularized in 'The Little Book That Beats the Market' (2005); holds a basket of 20-30 names "
                   "ranked jointly on EBIT/EV and EBIT/capital.",
        "methodology": "Earnings yield = EBIT ÷ enterprise value (market cap + net debt); return on capital = "
                       "EBIT ÷ (total assets − current liabilities). Both from originally-filed annual statements, "
                       "priced point-in-time. Names clearing the floors qualify; ranked by the sum of the two yields.",
        "parameters": {"tickers": [], "model": "magic_formula", "min_earnings_yield": 0.04, "min_roc": 0.10,
                       "max_positions": 20, "take_profit_pct": 0.60, "stop_loss_pct": 0.25, "max_hold_days": 365},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "long_term",
        "name": "Value Composite",
        "description": "Owns companies cheap on both free-cash-flow yield and earnings yield.",
        "history": "A two-ratio cousin of O'Shaughnessy's value composites — blending yields is more robust than "
                   "any single cheapness measure.",
        "methodology": "Free-cash-flow yield and earnings yield are computed from originally-filed annual figures "
                       "against the point-in-time price; both must be positive, ranked by their average.",
        "parameters": {"tickers": [], "model": "value_composite", "max_positions": 15,
                       "take_profit_pct": 0.50, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "short_term",
        "name": "12-1 Momentum",
        "description": "The classic cross-sectional momentum factor: strong over twelve months, skipping the latest one.",
        "history": "Jegadeesh & Titman (1993) documented that 3-12 month winners keep winning; the one-month skip "
                   "avoids short-term reversal. The backbone of every academic momentum factor since.",
        "methodology": "Rank by trailing 12-month return excluding the most recent month; positive scores qualify, "
                       "top names held equal-weight with stop-loss and take-profit guards.",
        "parameters": {"tickers": [], "model": "momentum_12_1", "max_positions": 10,
                       "take_profit_pct": 0.30, "stop_loss_pct": 0.15, "max_hold_days": 90},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "short_term",
        "name": "52-Week High",
        "description": "Buys names trading within a few percent of their one-year high.",
        "history": "George & Hwang (2004) showed proximity to the 52-week high predicts returns about as well as "
                   "past returns themselves — anchoring makes investors slow to bid stocks through old highs.",
        "methodology": "Eligible when the latest close is at least the minimum proximity (default 95%) of the "
                       "trailing 252-day high; ranked by proximity.",
        "parameters": {"tickers": [], "model": "high_52w", "min_proximity": 0.95, "max_positions": 10,
                       "take_profit_pct": 0.25, "stop_loss_pct": 0.12, "max_hold_days": 120},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "short_term",
        "name": "RSI-2 Mean Reversion",
        "description": "Buys deep short-term oversold dips in broad ETFs that remain in long-term uptrends.",
        "history": "Larry Connors' RSI(2) system: extreme two-day RSI readings inside an uptrend mark panic dips "
                   "that tend to snap back within days.",
        "methodology": "Eligible when the 2-day RSI falls to 10 or below while price holds above its 200-day "
                       "average; exits when the oversold reading clears (criteria exit) or on tight profit/stop bands.",
        "parameters": {"tickers": ["SPY", "QQQ", "DIA", "IWM"], "universe": "tickers", "model": "rsi_reversion",
                       "rsi_days": 2, "max_rsi": 10, "max_positions": 4,
                       "take_profit_pct": 0.05, "stop_loss_pct": 0.05, "max_hold_days": 10},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "income_quality",
        "name": "Dividend Dogs",
        "description": "Holds the highest yielders whose dividends are fully covered by free cash flow.",
        "history": "A point-in-time take on the 'Dogs of the Dow' tradition — harvest yield, but use cash-flow "
                   "coverage to dodge the classic yield-trap failure mode.",
        "methodology": "Dividend yield from originally-filed dividends paid against the point-in-time price; "
                       "requires free cash flow to cover the payout. Top yielders held equal-weight.",
        "parameters": {"tickers": [], "model": "dividend_yield", "min_yield": 0.03, "min_fcf_coverage": 1.0,
                       "max_positions": 10, "take_profit_pct": 0.40, "stop_loss_pct": 0.18, "max_hold_days": 365},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "risk_rotation",
        "name": "Dual Momentum (GEM)",
        "description": "Gary Antonacci's Global Equities Momentum: US stocks, international stocks, or bonds — whichever leads.",
        "history": "From 'Dual Momentum Investing' (2014): relative momentum picks the strongest asset, absolute "
                   "momentum steps aside to bonds/cash when nothing is rising.",
        "methodology": "Each day, rank SPY, EFA and AGG by trailing 12-month return; hold the leader only while its "
                       "own return is positive (absolute-momentum gate), otherwise sit in cash.",
        "parameters": {"tickers": ["SPY", "EFA", "AGG"], "universe": "tickers", "model": "dual_momentum",
                       "lookback_days": 252, "take_profit_pct": 0.99, "stop_loss_pct": 0.15, "max_hold_days": 365},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
    {
        "category": "risk_rotation",
        "name": "Faber Trend (GTAA)",
        "description": "Meb Faber's tactical asset allocation: hold each asset class only while it's above its long-term trend.",
        "history": "'A Quantitative Approach to Tactical Asset Allocation' (2007) — the most-downloaded SSRN paper "
                   "ever: a 10-month moving-average filter on five asset classes cut drawdowns dramatically.",
        "methodology": "US stocks, foreign stocks, bonds, real estate and commodities (SPY, EFA, AGG, VNQ, DBC) are "
                       "each held while price sits above the ~10-month (210-day) moving average; below it, that "
                       "sleeve rotates to cash.",
        "parameters": {"tickers": ["SPY", "EFA", "AGG", "VNQ", "DBC"], "universe": "tickers",
                       "model": "trend_following", "sma_days": 210, "max_positions": 5,
                       "take_profit_pct": 0.99, "stop_loss_pct": 0.20, "max_hold_days": 365},
        "metrics": {},
        "caveats": [*COMMON_CAVEATS, _NO_SEEDED_METRICS],
    },
]
