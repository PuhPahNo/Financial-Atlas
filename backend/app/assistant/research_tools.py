"""Strict, read-only research tools and grounded visualization artifacts.

The model sees compact normalized results. The browser receives charts/tables built
from the exact same Python objects, so visualization numbers never come from model text.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import pstdev
from typing import Any, Callable

from ..core.errors import NotFoundError, ValidationError
from ..core.matching import best_name_match
from ..paper_trading import accounts as account_service
from ..paper_trading import service as paper_service
from ..providers.base import Period
from ..services import company, filings, financials, market, prices, screener
from ..valuation import service as valuation_service

COLORS = ["#8b7cff", "#3ecf8e", "#f2b84b", "#ff7a90", "#55b7ff", "#c18cff"]


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {"type": "function", "name": name, "description": description, "parameters": parameters, "strict": True}


TICKER = {"type": "string", "minLength": 1, "maxLength": 12, "description": "Public market ticker symbol."}
PERIOD = {"type": "string", "enum": ["annual", "quarter"]}
NULLABLE_DATE = {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD, or null."}

RESEARCH_TOOLS = [
    _tool("get_company_snapshot", "Get a company's normalized profile and latest headline metrics.", _object_schema({"ticker": TICKER}, ["ticker"])),
    _tool(
        "get_financial_statements",
        "Get bounded normalized income, balance-sheet, or cash-flow statement history.",
        _object_schema({
            "ticker": TICKER,
            "statement": {"type": "string", "enum": ["income", "balance", "cashflow"]},
            "period": PERIOD,
            "limit": {"type": "integer", "minimum": 1, "maximum": 12},
        }, ["ticker", "statement", "period", "limit"]),
    ),
    _tool(
        "get_cash_flow_analysis",
        "Get joined income, balance-sheet, and cash-flow history plus quality, capital-allocation, leverage, and conversion metrics. It already includes the source fields; do not repeat it with statement calls for the same periods.",
        _object_schema({"ticker": TICKER, "period": PERIOD, "limit": {"type": "integer", "minimum": 1, "maximum": 12}}, ["ticker", "period", "limit"]),
    ),
    _tool("get_valuation", "Get Atlas valuation models, scenarios, assumptions, and current margin of safety.", _object_schema({"ticker": TICKER}, ["ticker"])),
    _tool(
        "get_price_history",
        "Get bounded price trend and risk statistics for a stock, ETF, index, or other supported ticker.",
        _object_schema({"ticker": TICKER, "range": {"type": "string", "enum": ["1m", "3m", "6m", "1y", "3y", "5y", "max"]}}, ["ticker", "range"]),
    ),
    _tool(
        "compare_securities",
        "Compare total return, annualized volatility, and drawdown for 2-6 stocks, ETFs, or indices over one range.",
        _object_schema({
            "tickers": {"type": "array", "items": TICKER, "minItems": 2, "maxItems": 6},
            "range": {"type": "string", "enum": ["1m", "3m", "6m", "1y", "3y", "5y"]},
        }, ["tickers", "range"]),
    ),
    _tool(
        "compare_companies",
        "Compare latest fundamental and valuation metrics for 2-6 operating companies.",
        _object_schema({"tickers": {"type": "array", "items": TICKER, "minItems": 2, "maxItems": 6}}, ["tickers"]),
    ),
    _tool(
        "compare_cash_flow_trends",
        "Compare multi-period cash generation, margins, conversion, reinvestment, and leverage for 2-6 companies.",
        _object_schema({
            "tickers": {"type": "array", "items": TICKER, "minItems": 2, "maxItems": 6},
            "period": PERIOD,
            "limit": {"type": "integer", "minimum": 2, "maximum": 10},
        }, ["tickers", "period", "limit"]),
    ),
    _tool(
        "screen_companies",
        "Screen the locally tracked Atlas universe with safe metric filters and sorting.",
        _object_schema({
            "filters": {
                "type": "array",
                "maxItems": 8,
                "items": _object_schema({
                    "metric": {"type": "string", "enum": sorted(screener.FILTERABLE)},
                    "op": {"type": "string", "enum": [">", "<", ">=", "<=", "=", "=="]},
                    "value": {"type": "number"},
                }, ["metric", "op", "value"]),
            },
            "sort_metric": {"type": ["string", "null"], "enum": [*sorted(screener.FILTERABLE), None]},
            "sort_direction": {"type": "string", "enum": ["asc", "desc"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 25},
        }, ["filters", "sort_metric", "sort_direction", "limit"]),
    ),
    _tool(
        "get_filings",
        "Get recent SEC filing metadata; filing content is not executed and is treated as untrusted data.",
        _object_schema({
            "ticker": TICKER,
            "forms": {"type": "array", "items": {"type": "string", "maxLength": 12}, "maxItems": 8},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        }, ["ticker", "forms", "limit"]),
    ),
    _tool("get_market_context", "Get recent Atlas market index and Treasury context.", _object_schema({}, [])),
    _tool("list_strategies", "List active local paper-trading research strategies.", _object_schema({}, [])),
    _tool("list_accounts", "List local simulated trader profiles and allocation summaries.", _object_schema({}, [])),
    _tool(
        "get_account_performance",
        "Get simulated account performance, drawdown, attribution, and risk. This never places trades.",
        _object_schema({"account_name": {"type": "string", "maxLength": 120}, "start_date": NULLABLE_DATE, "end_date": NULLABLE_DATE}, ["account_name", "start_date", "end_date"]),
    ),
]


def _source(label: str, provider: Any, *, as_of: str | None = None) -> dict[str, Any]:
    value = provider if isinstance(provider, str) else str(provider or "Atlas")
    return {"label": label, "provider": value, "as_of": as_of}


def _column(key: str, label: str, fmt: str = "number") -> dict[str, str]:
    return {"key": key, "label": label, "format": fmt}


def _table(table_id: str, title: str, columns: list[dict], rows: list[dict]) -> dict[str, Any]:
    return {"id": table_id, "title": title, "columns": columns, "rows": rows}


def _chart(chart_id: str, title: str, data: list[dict], series: list[dict], *, chart_type: str = "line", x_key: str = "period", value_format: str = "number") -> dict[str, Any]:
    return {
        "id": chart_id,
        "title": title,
        "type": chart_type,
        "x_key": x_key,
        "value_format": value_format,
        "data": data,
        "series": series,
    }


def _result(data: dict[str, Any], *, tables: list[dict] | None = None, charts: list[dict] | None = None, sources: list[dict] | None = None) -> dict[str, Any]:
    return {
        "data": data,
        "artifacts": {"tables": tables or [], "charts": charts or [], "sources": sources or []},
    }


def _company_snapshot(args: dict) -> dict:
    ticker = str(args["ticker"]).upper()
    raw = company.overview(ticker)
    profile, metrics = raw["profile"], raw["key_metrics"]
    row = {"ticker": ticker, "name": profile.get("name"), **metrics}
    columns = [
        _column("ticker", "Ticker", "ticker"), _column("price", "Price", "currency"),
        _column("market_cap", "Market cap", "compact_currency"), _column("pe", "P/E", "multiple"),
        _column("price_to_fcf", "Price / FCF", "multiple"), _column("ev_ebitda", "EV / EBITDA", "multiple"),
        _column("dividend_yield", "Dividend yield", "percent"), _column("net_debt", "Net debt", "compact_currency"),
    ]
    return _result(
        {"ticker": ticker, "profile": profile, "key_metrics": metrics, "served_by": raw.get("served_by")},
        tables=[_table(f"snapshot-{ticker}", f"{ticker} snapshot", columns, [row])],
        sources=[_source(f"{ticker} company and market data", raw.get("served_by"))],
    )


STATEMENT_FIELDS = {
    "income": [
        ("revenue", "Revenue", "compact_currency"), ("gross_profit", "Gross profit", "compact_currency"),
        ("operating_income", "Operating income", "compact_currency"), ("net_income", "Net income", "compact_currency"),
        ("eps_diluted", "Diluted EPS", "currency"), ("ebitda", "EBITDA", "compact_currency"),
    ],
    "balance": [
        ("cash_and_equivalents", "Cash", "compact_currency"), ("short_term_investments", "Short-term investments", "compact_currency"),
        ("total_assets", "Total assets", "compact_currency"), ("total_liabilities", "Total liabilities", "compact_currency"),
        ("total_debt", "Total debt", "compact_currency"), ("shareholder_equity", "Shareholder equity", "compact_currency"),
    ],
    "cashflow": [
        ("operating_cash_flow", "Operating cash flow", "compact_currency"), ("capital_expenditures", "Capital expenditures", "compact_currency"),
        ("free_cash_flow", "Free cash flow", "compact_currency"), ("stock_based_compensation", "Stock compensation", "compact_currency"),
        ("dividends_paid", "Dividends", "compact_currency"), ("share_repurchases", "Share repurchases", "compact_currency"),
    ],
}


def _financial_statements(args: dict) -> dict:
    ticker = str(args["ticker"]).upper()
    kind = str(args["statement"])
    period = Period(str(args["period"]))
    limit = int(args["limit"])
    rows, provider = financials.statements(ticker, kind, period)
    selected = []
    for raw in rows[:limit]:
        row = {"period": f"{raw.get('fiscal_year')} {raw.get('period')}", "fiscal_year": raw.get("fiscal_year"), "filing_date": raw.get("filing_date")}
        row.update({key: raw.get(key) for key, _, _ in STATEMENT_FIELDS[kind]})
        selected.append(row)
    columns = [_column("period", "Fiscal period", "text"), _column("filing_date", "Filed", "date")]
    columns += [_column(key, label, fmt) for key, label, fmt in STATEMENT_FIELDS[kind]]
    chart_rows = list(reversed(selected))
    series = [{"key": key, "label": label, "color": COLORS[i % len(COLORS)]} for i, (key, label, _) in enumerate(STATEMENT_FIELDS[kind][:4])]
    return _result(
        {"ticker": ticker, "statement": kind, "period": period.value, "rows": selected, "served_by": provider},
        tables=[_table(f"{kind}-{ticker}-{period.value}", f"{ticker} {kind} statement", columns, selected)],
        charts=[_chart(f"{kind}-trend-{ticker}", f"{ticker} {kind} trends", chart_rows, series, value_format="compact_currency")],
        sources=[_source(f"{ticker} {kind} statements", provider, as_of=selected[0].get("filing_date") if selected else None)],
    )


def _cash_flow_analysis(args: dict) -> dict:
    ticker = str(args["ticker"]).upper()
    period = Period(str(args["period"]))
    limit = int(args["limit"])
    raw = financials.cash_flow_analysis(ticker, period)
    periods = raw["periods"][:limit]
    rows = [{"period": f"{r.get('fiscal_year')} {r.get('period')}", **r} for r in periods]
    columns = [
        _column("period", "Fiscal period", "text"), _column("revenue", "Revenue", "compact_currency"),
        _column("operating_cash_flow", "Operating cash flow", "compact_currency"), _column("capex", "CapEx", "compact_currency"),
        _column("free_cash_flow", "Free cash flow", "compact_currency"), _column("fcf_margin", "FCF margin", "percent"),
        _column("fcf_conversion", "FCF conversion", "percent"), _column("net_debt_to_fcf", "Net debt / FCF", "multiple"),
        _column("sbc_pct_ocf", "SBC / OCF", "percent"), _column("payout_vs_fcf", "Payout / FCF", "percent"),
    ]
    charts = [
        _chart(
            f"cash-generation-{ticker}", f"{ticker} cash generation", list(reversed(rows)),
            [
                {"key": "operating_cash_flow", "label": "Operating cash flow", "color": COLORS[0]},
                {"key": "free_cash_flow", "label": "Free cash flow", "color": COLORS[1]},
                {"key": "capex", "label": "CapEx", "color": COLORS[2]},
            ], value_format="compact_currency",
        ),
        _chart(
            f"cash-quality-{ticker}", f"{ticker} cash-flow quality", list(reversed(rows)),
            [
                {"key": "fcf_margin", "label": "FCF margin", "color": COLORS[0]},
                {"key": "fcf_conversion", "label": "FCF conversion", "color": COLORS[1]},
            ], value_format="percent",
        ),
    ]
    return _result(
        {"ticker": ticker, "period": period.value, "periods": periods, "scorecard": raw.get("scorecard"), "served_by": raw.get("served_by")},
        tables=[_table(f"cash-flow-{ticker}", f"{ticker} cash-flow analysis", columns, rows)], charts=charts,
        sources=[_source(f"{ticker} SEC cash-flow analysis", raw.get("served_by"))],
    )


def _valuation(args: dict) -> dict:
    ticker = str(args["ticker"]).upper()
    raw = valuation_service.valuate(ticker)
    scenarios = raw.get("scenarios") or {}
    models = [
        {
            "model": item.get("model"),
            "fair_value": item.get("fair_value_per_share"),
            "applicable": item.get("applicable"),
            "reason": item.get("reason"),
        }
        for item in raw.get("models", [])
    ]
    summary = {
        "ticker": ticker,
        "current_price": raw.get("current_price"),
        "blended_fair_value": raw.get("blended_fair_value"),
        "margin_of_safety": raw.get("margin_of_safety"),
        "scenarios": scenarios,
        "models": models,
        "assumptions": raw.get("assumptions"),
        "note": raw.get("note"),
    }
    scenario_rows = [{"scenario": name.title(), "fair_value": value} for name, value in scenarios.items()]
    tables = [_table(
        f"valuation-{ticker}", f"{ticker} valuation range",
        [_column("scenario", "Scenario", "text"), _column("fair_value", "Fair value / share", "currency")], scenario_rows,
    )]
    charts = [_chart(
        f"valuation-{ticker}", f"{ticker} valuation range", scenario_rows,
        [{"key": "fair_value", "label": "Fair value / share", "color": COLORS[0]}],
        chart_type="bar", x_key="scenario", value_format="currency",
    )]
    return _result(summary, tables=tables, charts=charts, sources=[_source(f"{ticker} Atlas valuation models", "derived from SEC and market data")])


def _downsample(rows: list[dict], limit: int = 120) -> list[dict]:
    if len(rows) <= limit:
        return rows
    step = (len(rows) - 1) / (limit - 1)
    indexes = sorted({round(i * step) for i in range(limit)})
    return [rows[index] for index in indexes]


def _close_points(ticker: str, range_value: str) -> tuple[list[dict], str]:
    raw, provider = prices.price_history(ticker, range=range_value, interval="1d")
    points = [
        {"date": bar.get("date"), "close": bar.get("adjusted_close") if bar.get("adjusted_close") is not None else bar.get("close")}
        for bar in raw.get("bars", [])
    ]
    points = [point for point in points if point["date"] and point["close"] is not None]
    range_days = {"1m": 31, "3m": 93, "6m": 186, "1y": 366, "3y": 1097, "5y": 1830}
    if range_value in range_days:
        cutoff = (date.today() - timedelta(days=range_days[range_value])).isoformat()
        points = [point for point in points if str(point["date"]) >= cutoff]
    return points, provider


def _risk_stats(points: list[dict]) -> dict[str, Any]:
    closes = [float(point["close"]) for point in points]
    if not closes:
        return {"observations": 0, "total_return": None, "annualized_volatility": None, "max_drawdown": None}
    returns = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes)) if closes[i - 1] != 0]
    peak = closes[0]
    max_drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        max_drawdown = min(max_drawdown, (close / peak) - 1 if peak else 0)
    return {
        "observations": len(closes),
        "start": points[0]["date"],
        "end": points[-1]["date"],
        "start_price": closes[0],
        "end_price": closes[-1],
        "total_return": (closes[-1] / closes[0]) - 1 if closes[0] else None,
        "annualized_volatility": pstdev(returns) * math.sqrt(252) if len(returns) > 1 else None,
        "max_drawdown": max_drawdown,
        "high": max(closes),
        "low": min(closes),
    }


def _price_history(args: dict) -> dict:
    ticker, range_value = str(args["ticker"]).upper(), str(args["range"])
    points, provider = _close_points(ticker, range_value)
    stats = _risk_stats(points)
    sampled = _downsample(points)
    return _result(
        {"ticker": ticker, "range": range_value, "statistics": stats, "points": sampled, "served_by": provider},
        tables=[_table(
            f"price-stats-{ticker}", f"{ticker} price statistics",
            [_column("ticker", "Ticker", "ticker"), _column("total_return", "Total return", "percent"), _column("annualized_volatility", "Annualized volatility", "percent"), _column("max_drawdown", "Max drawdown", "percent"), _column("end_price", "Latest price", "currency")],
            [{"ticker": ticker, **stats}],
        )],
        charts=[_chart(f"price-{ticker}-{range_value}", f"{ticker} price · {range_value}", sampled, [{"key": "close", "label": ticker, "color": COLORS[0]}], x_key="date", value_format="currency")],
        sources=[_source(f"{ticker} adjusted daily prices", provider, as_of=stats.get("end"))],
    )


def _unique_tickers(values: list[Any], *, minimum: int = 1) -> list[str]:
    tickers = list(dict.fromkeys(str(value).strip().upper() for value in values if str(value).strip()))
    if len(tickers) < minimum or len(tickers) > 6:
        raise ValidationError(f"Expected {minimum}-6 unique tickers")
    return tickers


def _compare_securities(args: dict) -> dict:
    tickers = _unique_tickers(args["tickers"], minimum=2)
    range_value = str(args["range"])
    rows, sources, series = [], [], []
    normalized_by_date: dict[str, dict[str, Any]] = {}
    failures = []
    for index, ticker in enumerate(tickers):
        try:
            points, provider = _close_points(ticker, range_value)
            stats = _risk_stats(points)
            rows.append({"ticker": ticker, **stats})
            if points:
                base = float(points[0]["close"])
                for point in _downsample(points, 100):
                    normalized_by_date.setdefault(point["date"], {"date": point["date"]})[ticker] = (float(point["close"]) / base) * 100 if base else None
            sources.append(_source(f"{ticker} adjusted daily prices", provider, as_of=stats.get("end")))
            series.append({"key": ticker, "label": ticker, "color": COLORS[index]})
        except Exception as exc:  # one unsupported ticker should not erase valid comparisons
            failures.append({"ticker": ticker, "error": str(exc)})
    if not rows:
        raise NotFoundError("No supported price history was available for the requested securities")
    chart_rows = [normalized_by_date[key] for key in sorted(normalized_by_date)]
    return _result(
        {"range": range_value, "securities": rows, "failures": failures},
        tables=[_table(
            f"security-comparison-{range_value}", f"Security comparison · {range_value}",
            [_column("ticker", "Ticker", "ticker"), _column("total_return", "Total return", "percent"), _column("annualized_volatility", "Annualized volatility", "percent"), _column("max_drawdown", "Max drawdown", "percent"), _column("end_price", "Latest price", "currency")], rows,
        )],
        charts=[_chart(f"normalized-{range_value}-{'-'.join(tickers)}", f"Growth of 100 · {range_value}", chart_rows, series, x_key="date", value_format="index")],
        sources=sources,
    )


def _compare_companies(args: dict) -> dict:
    tickers = _unique_tickers(args["tickers"], minimum=2)
    rows, failures = [], []
    for ticker in tickers:
        try:
            row = screener.build_snapshot(ticker)
            rows.append(row)
        except Exception as exc:
            failures.append({"ticker": ticker, "error": str(exc)})
    if not rows:
        raise NotFoundError("No company fundamentals were available for the requested tickers")
    columns = [
        _column("ticker", "Ticker", "ticker"), _column("market_cap", "Market cap", "compact_currency"),
        _column("pe", "P/E", "multiple"), _column("price_to_fcf", "Price / FCF", "multiple"),
        _column("ev_ebitda", "EV / EBITDA", "multiple"), _column("fcf_margin", "FCF margin", "percent"),
        _column("fcf_conversion", "FCF conversion", "percent"), _column("margin_of_safety", "Margin of safety", "percent"),
    ]
    charts = [
        _chart(f"fcf-margin-{'-'.join(tickers)}", "Free-cash-flow margin", rows, [{"key": "fcf_margin", "label": "FCF margin", "color": COLORS[1]}], chart_type="bar", x_key="ticker", value_format="percent"),
        _chart(f"price-fcf-{'-'.join(tickers)}", "Price to free cash flow", rows, [{"key": "price_to_fcf", "label": "Price / FCF", "color": COLORS[0]}], chart_type="bar", x_key="ticker", value_format="multiple"),
    ]
    return _result(
        {"companies": rows, "failures": failures}, tables=[_table(f"company-comparison-{'-'.join(tickers)}", "Company comparison", columns, rows)], charts=charts,
        sources=[_source("Atlas company snapshots", "SEC EDGAR, market prices, and derived valuation")],
    )


def _compare_cash_flow_trends(args: dict) -> dict:
    tickers = _unique_tickers(args["tickers"], minimum=2)
    period = Period(str(args["period"]))
    limit = int(args["limit"])
    companies: list[dict] = []
    latest_rows: list[dict] = []
    cash_by_period: dict[str, dict[str, Any]] = {}
    margin_by_period: dict[str, dict[str, Any]] = {}
    sources: list[dict] = []
    failures: list[dict] = []
    for index, ticker in enumerate(tickers):
        try:
            raw = financials.cash_flow_analysis(ticker, period)
            rows = raw["periods"][:limit]
            companies.append({"ticker": ticker, "periods": rows, "scorecard": raw.get("scorecard")})
            if rows:
                latest_rows.append({"ticker": ticker, **rows[0]})
            for row in reversed(rows):
                label = f"{row.get('fiscal_year')} {row.get('period')}"
                cash_by_period.setdefault(label, {"period": label})[ticker] = row.get("free_cash_flow")
                margin_by_period.setdefault(label, {"period": label})[ticker] = row.get("fcf_margin")
            sources.append(_source(f"{ticker} SEC cash-flow analysis", raw.get("served_by")))
        except Exception as exc:
            failures.append({"ticker": ticker, "error": str(exc)})
    if not companies:
        raise NotFoundError("No cash-flow history was available for the requested companies")
    series = [{"key": ticker, "label": ticker, "color": COLORS[index]} for index, ticker in enumerate(tickers)]
    columns = [
        _column("ticker", "Ticker", "ticker"), _column("fiscal_year", "Latest fiscal year", "integer"),
        _column("free_cash_flow", "Free cash flow", "compact_currency"), _column("fcf_margin", "FCF margin", "percent"),
        _column("fcf_conversion", "FCF conversion", "percent"), _column("reinvestment_rate", "Reinvestment rate", "percent"),
        _column("sbc_pct_ocf", "SBC / OCF", "percent"), _column("net_debt_to_fcf", "Net debt / FCF", "multiple"),
    ]
    return _result(
        {"period": period.value, "companies": companies, "failures": failures},
        tables=[_table(f"cash-comparison-{'-'.join(tickers)}", "Latest cash-flow comparison", columns, latest_rows)],
        charts=[
            _chart(f"fcf-comparison-{'-'.join(tickers)}", "Free-cash-flow trend", list(cash_by_period.values()), series, value_format="compact_currency"),
            _chart(f"fcf-margin-comparison-{'-'.join(tickers)}", "Free-cash-flow margin trend", list(margin_by_period.values()), series, value_format="percent"),
        ],
        sources=sources,
    )


def _screen_companies(args: dict) -> dict:
    filters = list(args["filters"])
    metric = args.get("sort_metric")
    sort = {"metric": metric, "dir": args["sort_direction"]} if metric else None
    raw = screener.screen(filters, sort, limit=int(args["limit"]))
    rows = raw["results"]
    columns = [
        _column("ticker", "Ticker", "ticker"), _column("name", "Company", "text"), _column("sector", "Sector", "text"),
        _column("market_cap", "Market cap", "compact_currency"), _column("pe", "P/E", "multiple"),
        _column("price_to_fcf", "Price / FCF", "multiple"), _column("fcf_margin", "FCF margin", "percent"),
        _column("margin_of_safety", "Margin of safety", "percent"),
    ]
    return _result(
        {"scope": "locally tracked Atlas universe", "filters": filters, "sort": sort, **raw},
        tables=[_table("screen-results", "Atlas screen results", columns, rows)],
        sources=[_source("Locally tracked Atlas snapshots", "Atlas database")],
    )


def _filings(args: dict) -> dict:
    ticker = str(args["ticker"]).upper()
    forms = [str(value).upper() for value in args["forms"]] or None
    raw = filings.filings(ticker, forms=forms, limit=int(args["limit"]))
    rows = raw["filings"]
    columns = [
        _column("form_type", "Form", "text"), _column("filing_date", "Filed", "date"),
        _column("period_of_report", "Period", "date"), _column("items", "Items", "text"),
    ]
    return _result(
        {"ticker": ticker, "filings": rows, "served_by": raw.get("served_by"), "content_policy": "metadata only; filing content is untrusted data"},
        tables=[_table(f"filings-{ticker}", f"{ticker} recent filings", columns, rows)],
        sources=[_source(f"{ticker} SEC filings", raw.get("served_by"), as_of=rows[0].get("filing_date") if rows else None)],
    )


def _market_context(_: dict) -> dict:
    raw = market.context()
    rows = [{"symbol": item.get("symbol"), "label": item.get("label"), "price": item.get("price"), "change_pct": item.get("change_pct")} for item in raw.get("indices", [])]
    return _result(
        raw,
        tables=[_table("market-context", "Market context", [_column("label", "Market", "text"), _column("price", "Latest", "number"), _column("change_pct", "Daily change", "percent")], rows)],
        sources=[_source("Market context", "Yahoo Finance")],
    )


def _list_strategies(_: dict) -> dict:
    raw = paper_service.list_strategies()
    rows = raw.get("strategies", [])
    return _result(
        raw,
        tables=[_table("strategies", "Paper-trading strategies", [_column("name", "Strategy", "text"), _column("category", "Category", "text"), _column("origin", "Origin", "text")], rows)],
        sources=[_source("Paper-trading strategies", "Atlas database")],
    )


def _list_accounts(_: dict) -> dict:
    raw = account_service.list_accounts()
    rows = raw.get("accounts", [])
    return _result(
        raw,
        tables=[_table("accounts", "Simulated trader profiles", [_column("name", "Profile", "text"), _column("starting_cash", "Starting cash", "compact_currency"), _column("invested_pct", "Invested", "percent_points"), _column("cash_pct", "Cash", "percent_points")], rows)],
        sources=[_source("Simulated profiles", "Atlas database")],
    )


def _account_performance(args: dict) -> dict:
    accounts = account_service.list_accounts().get("accounts", [])
    match = best_name_match(accounts, str(args["account_name"]))
    if not match:
        raise NotFoundError(f"Trader account '{args['account_name']}' not found")
    start = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
    end = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
    raw = account_service.account_performance(int(match["id"]), start=start, end=end)
    summary = {
        "profile": match.get("name"), "window": raw.get("window"), "total_return": raw.get("total_return"),
        "benchmark_return": raw.get("benchmark_return"), "alpha": raw.get("alpha"), "max_drawdown": raw.get("max_drawdown"),
        "risk": raw.get("risk"), "attribution": raw.get("attribution"), "warnings": raw.get("warnings"),
    }
    curve = raw.get("equity", [])
    return _result(
        summary,
        tables=[_table("account-performance", f"{match.get('name')} performance", [_column("profile", "Profile", "text"), _column("total_return", "Return", "percent"), _column("benchmark_return", "Benchmark", "percent"), _column("alpha", "Alpha", "percent"), _column("max_drawdown", "Max drawdown", "percent")], [summary])],
        charts=[_chart("account-equity", f"{match.get('name')} growth", curve, [{"key": "equity", "label": "Profile", "color": COLORS[0]}, {"key": "benchmark_equity", "label": "Benchmark", "color": COLORS[1]}], x_key="date", value_format="currency")],
        sources=[_source(f"{match.get('name')} simulated performance", "Atlas backtest engine", as_of=(raw.get("window") or {}).get("end"))],
    )


EXECUTORS: dict[str, Callable[[dict], dict]] = {
    "get_company_snapshot": _company_snapshot,
    "get_financial_statements": _financial_statements,
    "get_cash_flow_analysis": _cash_flow_analysis,
    "get_valuation": _valuation,
    "get_price_history": _price_history,
    "compare_securities": _compare_securities,
    "compare_companies": _compare_companies,
    "compare_cash_flow_trends": _compare_cash_flow_trends,
    "screen_companies": _screen_companies,
    "get_filings": _filings,
    "get_market_context": _market_context,
    "list_strategies": _list_strategies,
    "list_accounts": _list_accounts,
    "get_account_performance": _account_performance,
}


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
    """Validate the small JSON Schema subset used by strict research tools.

    Responses strict mode is the first boundary. This independent check keeps
    limits fail-closed if a provider response is malformed or replayed outside
    that contract.
    """
    declared = schema.get("type")
    allowed = declared if isinstance(declared, list) else [declared]
    if value is None and "null" in allowed:
        return

    actual = (
        "object" if isinstance(value, dict)
        else "array" if isinstance(value, list)
        else "boolean" if isinstance(value, bool)
        else "integer" if isinstance(value, int)
        else "number" if isinstance(value, float)
        else "string" if isinstance(value, str)
        else "null" if value is None
        else type(value).__name__
    )
    type_matches = actual in allowed or (actual == "integer" and "number" in allowed)
    if not type_matches:
        raise ValidationError(f"{path} must be {', '.join(str(item) for item in allowed)}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path} must be one of the supported values")

    if actual == "object":
        properties = schema.get("properties") or {}
        missing = [name for name in schema.get("required") or [] if name not in value]
        if missing:
            raise ValidationError(f"{path} is missing required field: {missing[0]}")
        unknown = set(value) - set(properties)
        if schema.get("additionalProperties") is False and unknown:
            raise ValidationError(f"{path} has unsupported field: {sorted(unknown)[0]}")
        for name, item in value.items():
            if name in properties:
                _validate_schema(item, properties[name], f"{path}.{name}")
    elif actual == "array":
        if len(value) < int(schema.get("minItems", 0)):
            raise ValidationError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValidationError(f"{path} has too many items")
        for index, item in enumerate(value):
            _validate_schema(item, schema.get("items") or {}, f"{path}[{index}]")
    elif actual == "string":
        if len(value) < int(schema.get("minLength", 0)):
            raise ValidationError(f"{path} is too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValidationError(f"{path} is too long")
    elif actual in {"integer", "number"}:
        if not math.isfinite(value):
            raise ValidationError(f"{path} must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"{path} is below the minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"{path} exceeds the maximum")


def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    executor = EXECUTORS.get(name)
    if executor is None:
        raise ValidationError(f"Unknown research tool: {name}")
    schema = next(item["parameters"] for item in RESEARCH_TOOLS if item["name"] == name)
    _validate_schema(arguments, schema)
    return executor(arguments)
