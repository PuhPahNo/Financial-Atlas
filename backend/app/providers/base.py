"""Normalized provider-domain models (PRD 02 §4, PRD 03 §5).

Providers adapt one external source and return these schema-valid domain
objects — never raw upstream JSON. The registry owns explicit fallback chains.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Period(str, Enum):
    ANNUAL = "annual"
    QUARTER = "quarter"


class Interval(str, Enum):
    DAY = "1d"
    WEEK = "1wk"
    MONTH = "1mo"


# ---------------------------------------------------------------------------
# Normalized domain models
# ---------------------------------------------------------------------------
class CompanyProfile(BaseModel):
    ticker: str
    cik: Optional[str] = None
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    sic_code: Optional[str] = None
    description: Optional[str] = None
    exchange: Optional[str] = None
    currency: str = "USD"
    shares_outstanding: Optional[float] = None
    foreign_filer: bool = False  # files 20-F/40-F (ADR) — per-share valuation unreliable


class PriceBar(BaseModel):
    date: str  # ISO date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    adjusted_close: Optional[float] = None
    volume: Optional[int] = None


class Quote(BaseModel):
    price: Optional[float] = None
    previous_close: Optional[float] = None
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None
    currency: str = "USD"


class _PeriodModel(BaseModel):
    fiscal_year: int
    period: str  # FY, Q1..Q4
    filing_date: Optional[str] = None
    filing_ref: Optional[str] = None
    source: Optional[str] = None


class IncomeStatement(_PeriodModel):
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    interest_expense: Optional[float] = None
    pretax_income: Optional[float] = None
    net_income: Optional[float] = None
    eps_basic: Optional[float] = None
    eps_diluted: Optional[float] = None
    weighted_average_shares: Optional[float] = None
    weighted_average_shares_diluted: Optional[float] = None
    ebitda: Optional[float] = None


class BalanceSheet(_PeriodModel):
    cash_and_equivalents: Optional[float] = None
    short_term_investments: Optional[float] = None
    total_current_assets: Optional[float] = None
    total_assets: Optional[float] = None
    total_current_liabilities: Optional[float] = None
    total_liabilities: Optional[float] = None
    short_term_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    total_debt: Optional[float] = None
    shareholder_equity: Optional[float] = None


class CashFlowStatement(_PeriodModel):
    operating_cash_flow: Optional[float] = None
    capital_expenditures: Optional[float] = None
    free_cash_flow: Optional[float] = None
    depreciation_and_amortization: Optional[float] = None
    stock_based_compensation: Optional[float] = None
    dividends_paid: Optional[float] = None
    share_repurchases: Optional[float] = None
    debt_issued: Optional[float] = None
    debt_repaid: Optional[float] = None
    change_in_working_capital: Optional[float] = None


class InsiderTransaction(BaseModel):
    insider_name: Optional[str] = None
    insider_title: Optional[str] = None
    relationship: Optional[str] = None  # Director / Officer / 10% Owner
    transaction_date: Optional[str] = None
    transaction_code: Optional[str] = None  # P, S, A, M, F, G, ...
    acquired_disposed: Optional[str] = None  # A or D
    shares: Optional[float] = None
    price: Optional[float] = None
    value: Optional[float] = None
    shares_owned_after: Optional[float] = None
    is_open_market: bool = False  # P/S = open-market buy/sell
    filing_ref: Optional[str] = None
    filing_url: Optional[str] = None


class Filing(BaseModel):
    form_type: str
    filing_date: Optional[str] = None
    period_of_report: Optional[str] = None
    accession_no: Optional[str] = None
    primary_doc_url: Optional[str] = None
    items: Optional[str] = None  # 8-K item codes


class LargeStake(BaseModel):
    form_type: str  # SC 13D, SC 13G, SC 13D/A, ...
    filer: Optional[str] = None
    filing_date: Optional[str] = None
    accession_no: Optional[str] = None
    primary_doc_url: Optional[str] = None
    intent: Optional[str] = None  # "active" (13D) / "passive" (13G)


class NewsArticle(BaseModel):
    headline: str
    summary: Optional[str] = None
    source: Optional[str] = None
    url: str
    published_at: Optional[str] = None
    image: Optional[str] = None


class AnalystSnapshot(BaseModel):
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    target_consensus: Optional[float] = None
    target_median: Optional[float] = None
    strong_buy: Optional[int] = None
    buy: Optional[int] = None
    hold: Optional[int] = None
    sell: Optional[int] = None
    strong_sell: Optional[int] = None
    rating: Optional[str] = None  # derived label (e.g. "Buy")


class Peer(BaseModel):
    ticker: str
    name: Optional[str] = None
    price: Optional[float] = None
    market_cap: Optional[float] = None


class Mover(BaseModel):
    ticker: str
    name: Optional[str] = None
    price: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
