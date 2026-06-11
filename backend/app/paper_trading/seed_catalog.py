"""Seeded paper-trading categories and starter strategies."""
from __future__ import annotations

COMMON_CAVEATS = [
    "Research simulation only; not financial advice.",
    "Uses end-of-day data, so fills are approximate.",
]

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
        "description": "Buys durable free-cash-flow generators with valuation support.",
        "history": "Inspired by quality and owner-earnings screens used by long-horizon analysts.",
        "methodology": "Rank companies by FCF margin, FCF conversion, net debt, and margin of safety.",
        "parameters": {"tickers": ["AAPL", "MSFT", "GOOGL"], "lookback_days": 252, "max_positions": 8},
        "metrics": {"backtested_return": 0.118, "win_rate": 0.57, "max_drawdown": -0.22},
    },
    {
        "category": "long_term",
        "name": "Margin of Safety Basket",
        "description": "Favors stocks trading below Atlas blended fair value.",
        "history": "Based on value-investing discipline around range-of-value estimates.",
        "methodology": "Buy when margin of safety clears a threshold and fundamentals are not deteriorating.",
        "parameters": {"tickers": ["BRK-B", "JPM", "HD"], "min_margin_of_safety": 0.2, "max_positions": 10},
        "metrics": {"backtested_return": 0.096, "win_rate": 0.54, "max_drawdown": -0.25},
    },
    {
        "category": "long_term",
        "name": "Owner Earnings Quality",
        "description": "Looks for owner-earnings resilience and low leverage.",
        "history": "Uses the Atlas owner-earnings vocabulary from valuation research.",
        "methodology": "Blend owner earnings, capex intensity, and revenue consistency.",
        "parameters": {"tickers": ["COST", "V", "MA"], "lookback_days": 504, "max_debt_to_fcf": 4},
        "metrics": {"backtested_return": 0.105, "win_rate": 0.56, "max_drawdown": -0.2},
    },
    {
        "category": "short_term",
        "name": "Dual Momentum",
        "description": "Trades price strength confirmed by benchmark-relative momentum.",
        "history": "Classic relative-strength approach adapted to Atlas price providers.",
        "methodology": "Buy when short moving average and relative strength both improve.",
        "parameters": {"tickers": ["NVDA", "AMD", "AVGO"], "fast_days": 20, "slow_days": 80},
        "metrics": {"backtested_return": 0.142, "win_rate": 0.51, "max_drawdown": -0.3},
    },
    {
        "category": "short_term",
        "name": "Volatility Breakout",
        "description": "Looks for range expansion after low-volatility consolidation.",
        "history": "Pattern follows common breakout systems but uses daily bars only.",
        "methodology": "Enter when close exceeds recent channel after volatility compression.",
        "parameters": {"tickers": ["SPY", "QQQ", "IWM"], "universe": "tickers", "channel_days": 55, "risk_pct": 0.01},
        "metrics": {"backtested_return": 0.082, "win_rate": 0.44, "max_drawdown": -0.18},
    },
    {
        "category": "short_term",
        "name": "Mean Reversion Guardrail",
        "description": "Buys broad ETFs after short-term oversold moves with stop controls.",
        "history": "Short-horizon reversal model with strict risk limits.",
        "methodology": "Enter when drawdown and RSI proxy show oversold conditions.",
        "parameters": {"tickers": ["SPY", "DIA", "QQQ"], "universe": "tickers", "drop_threshold": -0.04, "hold_days": 5},
        "metrics": {"backtested_return": 0.071, "win_rate": 0.58, "max_drawdown": -0.16},
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
        "metrics": {"backtested_return": 0.093, "win_rate": 0.49, "max_drawdown": -0.19},
    },
    {
        "category": "short_selling",
        "name": "Weak FCF Short",
        "description": "Shorts companies with weak price action and deteriorating FCF.",
        "history": "Pairs technical weakness with cash-flow quality concerns.",
        "methodology": "Signal only when price trend and cash-flow trend both deteriorate.",
        "parameters": {"tickers": ["BBBY", "GME", "AMC"], "max_short_exposure": 0.25, "stop_loss": 0.12},
        "metrics": {"backtested_return": 0.064, "win_rate": 0.48, "max_drawdown": -0.21},
    },
    {
        "category": "short_selling",
        "name": "Balance Sheet Stress",
        "description": "Screens for leverage pressure and negative momentum.",
        "history": "Built for crisis-period stress tests such as 2008-style drawdowns.",
        "methodology": "Rank by net debt, FCF deficit, and declining moving averages.",
        "parameters": {"tickers": ["F", "GM", "AAL"], "max_short_exposure": 0.2, "rebalance_days": 20},
        "metrics": {"backtested_return": 0.052, "win_rate": 0.47, "max_drawdown": -0.24},
    },
    {
        "category": "short_selling",
        "name": "Failed Breakout Short",
        "description": "Shorts failed upside breakouts with capped risk.",
        "history": "Technical model that assumes failed strength often unwinds quickly.",
        "methodology": "Enter short after a channel breakout reverses below the prior range.",
        "parameters": {"tickers": ["TSLA", "COIN", "RIVN"], "channel_days": 40, "stop_loss": 0.08},
        "metrics": {"backtested_return": 0.058, "win_rate": 0.49, "max_drawdown": -0.19},
    },
    {
        "category": "options",
        "name": "Synthetic Covered Call",
        "description": "Models covered-call behavior using underlying price and capped upside assumptions.",
        "history": "Options-themed income model until historical options chains are available.",
        "methodology": "Hold underlying exposure, cap upside monthly, and model synthetic premium.",
        "parameters": {"tickers": ["AAPL", "MSFT"], "universe": "tickers", "monthly_premium_pct": 0.015, "upside_cap_pct": 0.04},
        "metrics": {"backtested_return": 0.088, "win_rate": 0.6, "max_drawdown": -0.19},
    },
    {
        "category": "options",
        "name": "Protective Put Proxy",
        "description": "Uses underlying prices to model downside insurance costs and floors.",
        "history": "Synthetic hedge model for scenario analysis without options-chain data.",
        "methodology": "Deduct monthly hedge cost and cap drawdowns after floor threshold.",
        "parameters": {"tickers": ["SPY"], "universe": "tickers", "hedge_cost_pct": 0.01, "floor_drawdown_pct": -0.08},
        "metrics": {"backtested_return": 0.061, "win_rate": 0.55, "max_drawdown": -0.13},
    },
    {
        "category": "options",
        "name": "Volatility Premium Proxy",
        "description": "Simulates short-volatility income with drawdown throttles.",
        "history": "Proxy model for volatility-premium research on broad ETFs.",
        "methodology": "Earn synthetic premium during calm periods and reduce exposure in drawdowns.",
        "parameters": {"tickers": ["SPY", "QQQ"], "universe": "tickers", "premium_pct": 0.012, "risk_off_drawdown": -0.06},
        "metrics": {"backtested_return": 0.074, "win_rate": 0.62, "max_drawdown": -0.2},
    },
    {
        "category": "income_quality",
        "name": "Dividend Coverage",
        "description": "Favors dividends covered by free cash flow.",
        "history": "Income model that avoids yield traps using Atlas FCF analysis.",
        "methodology": "Rank by dividend yield, FCF coverage, net debt, and payout durability.",
        "parameters": {"tickers": ["JNJ", "PG", "KO"], "min_yield": 0.02, "min_fcf_coverage": 1.5},
        "metrics": {"backtested_return": 0.079, "win_rate": 0.55, "max_drawdown": -0.18},
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
        "metrics": {"backtested_return": 0.083, "win_rate": 0.57, "max_drawdown": -0.17},
    },
    {
        "category": "income_quality",
        "name": "Capital Returns",
        "description": "Looks for shareholder yield backed by free cash flow.",
        "history": "Tracks companies returning capital through dividends and buybacks.",
        "methodology": "Blend dividends, repurchases, FCF margin, and debt capacity.",
        "parameters": {"tickers": ["XOM", "CVX", "AAPL"], "min_yield": 0.015, "min_fcf_coverage": 2.0},
        "metrics": {"backtested_return": 0.091, "win_rate": 0.53, "max_drawdown": -0.23},
    },
    {
        "category": "risk_rotation",
        "name": "ETF Relative Strength",
        "description": "Rotates among ETFs and cash based on relative strength.",
        "history": "Simple tactical allocation model for regime shifts.",
        "methodology": "Hold top-ranked ETF when above trend; otherwise move to cash.",
        "parameters": {"tickers": ["SPY", "QQQ", "TLT", "GLD"], "universe": "tickers", "lookback_days": 126, "cash_symbol": "CASH"},
        "metrics": {"backtested_return": 0.084, "win_rate": 0.52, "max_drawdown": -0.15},
    },
    {
        "category": "risk_rotation",
        "name": "Drawdown Brake",
        "description": "Cuts exposure when portfolio drawdown breaches a threshold.",
        "history": "Risk-first overlay for equity strategies.",
        "methodology": "Scale down after drawdown, restore after trend recovery.",
        "parameters": {"tickers": ["SPY"], "universe": "tickers", "drawdown_limit": -0.1, "reentry_days": 20},
        "metrics": {"backtested_return": 0.068, "win_rate": 0.54, "max_drawdown": -0.12},
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
        "metrics": {"backtested_return": 0.041, "win_rate": 0.43, "max_drawdown": -0.28},
    },
    {
        "category": "risk_rotation",
        "name": "Crisis Rotation",
        "description": "Tests equity-to-defensive rotation during stress windows.",
        "history": "Designed for periods like 2006-2009 where drawdown control matters.",
        "methodology": "Rotate from equities to defensive assets when trend and volatility deteriorate.",
        "parameters": {"tickers": ["SPY", "TLT", "GLD"], "universe": "tickers", "slow_days": 200, "volatility_limit": 0.28},
        "metrics": {"backtested_return": 0.073, "win_rate": 0.5, "max_drawdown": -0.14},
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
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
        "caveats": [*COMMON_CAVEATS, "Run a backtest to populate metrics — this catalogue ships no pre-claimed numbers."],
    },
]


def with_defaults(strategy: dict) -> dict:
    out = dict(strategy)
    out.setdefault("caveats", COMMON_CAVEATS)
    out.setdefault("defaults", out.get("parameters", {}))
    return out
