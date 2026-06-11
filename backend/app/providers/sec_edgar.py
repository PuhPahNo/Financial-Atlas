"""SEC EDGAR provider (PRD 02) — the authoritative free source.

Covers company profile, XBRL fundamentals (income / balance / cash-flow), and
ticker->CIK resolution. No API key; a descriptive User-Agent is required.

XBRL extraction notes (PRD 12 §9): companies tag concepts inconsistently, so each
field has an ordered list of candidate us-gaap tags and we take the first present.
Annual figures are taken from 10-K filings (duration ~365d for flows; fiscal-year-end
snapshots for instants); quarterly from 10-Q discrete-quarter durations.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

from ..core import cache
from ..core.config import settings
from ..core.errors import NotFoundError
from ..core.http import get_json, get_text
from .base import (
    BalanceSheet,
    CashFlowStatement,
    Capability,
    CompanyProfile,
    Filing,
    IncomeStatement,
    InsiderTransaction,
    LargeStake,
    Period,
)

# SEC Form 4 transaction codes (subset). P/S are open-market buys/sells.
OPEN_MARKET_CODES = {"P", "S"}
TRANSACTION_CODE_LABELS = {
    "P": "Open-market buy", "S": "Open-market sell", "A": "Grant/award",
    "M": "Option exercise", "F": "Tax withholding", "G": "Gift",
    "C": "Conversion", "X": "Option exercise", "D": "Disposition to issuer",
}

_UA = {"User-Agent": settings.sec_user_agent}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_MEM: dict[str, dict] = {}  # in-memory parsed companyfacts (per-process)


# --- concept tag maps (ordered by preference) ------------------------------
INCOME_TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_basic": ["EarningsPerShareBasic"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "weighted_average_shares": ["WeightedAverageNumberOfSharesOutstandingBasic"],
    "weighted_average_shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}
BALANCE_TAGS = {
    "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "short_term_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
    "total_current_assets": ["AssetsCurrent"],
    "total_assets": ["Assets"],
    "total_current_liabilities": ["LiabilitiesCurrent"],
    "total_liabilities": ["Liabilities"],
    "short_term_debt": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "shareholder_equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}
CASHFLOW_TAGS = {
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capital_expenditures": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "depreciation_and_amortization": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"],
    "stock_based_compensation": ["ShareBasedCompensation"],
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "share_repurchases": ["PaymentsForRepurchaseOfCommonStock"],
    "debt_issued": ["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt"],
    "debt_repaid": ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt"],
}


class SecEdgarProvider:
    name = "sec_edgar"
    capabilities = frozenset({
        Capability.PROFILE, Capability.INCOME, Capability.BALANCE, Capability.CASHFLOW,
        Capability.INSIDER, Capability.INSTITUTIONAL, Capability.FILINGS,
    })

    # -- ticker / cik --------------------------------------------------------
    def _ticker_map(self) -> dict[str, dict]:
        def load():
            data = get_json(_TICKERS_URL, headers=_UA, provider=self.name)
            return {row["ticker"].upper(): {"cik": f'{int(row["cik_str"]):010d}', "title": row["title"]}
                    for row in data.values()}
        return cache.get_or_set("edgar", "ticker_map", ttl_seconds=7 * 86400, loader=load).value

    def resolve_cik(self, ticker: str) -> dict:
        tmap = self._ticker_map()
        norm = ticker.strip().upper()
        # EDGAR uses hyphens for share classes (BRK-B); accept the common dot form too.
        info = tmap.get(norm) or tmap.get(norm.replace(".", "-")) or tmap.get(norm.replace("-", "."))
        if not info:
            raise NotFoundError(f"Ticker {ticker} not found in SEC ticker map", ticker=ticker)
        return info

    def search_tickers(self, query: str, limit: int = 10) -> list[dict]:
        q = query.strip().upper()
        if not q:
            return []
        out = []
        for ticker, info in self._ticker_map().items():
            title = info.get("title", "")
            if ticker.startswith(q) or q in title.upper():
                # prefix ticker matches rank first
                rank = 0 if ticker.startswith(q) else 1
                out.append((rank, ticker, {"ticker": ticker, "name": title}))
        out.sort(key=lambda x: (x[0], len(x[1])))
        return [item[2] for item in out[:limit]]

    # -- profile -------------------------------------------------------------
    def get_company_profile(self, ticker: str) -> CompanyProfile:
        info = self.resolve_cik(ticker)
        cik = info["cik"]

        def load():
            return get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=_UA, provider=self.name)

        sub = cache.get_or_set("edgar", f"submissions:{cik}", ttl_seconds=30 * 86400, loader=load).value
        exchanges = sub.get("exchanges") or []
        recent_forms = set((sub.get("filings", {}).get("recent", {}) or {}).get("form", []))
        foreign = bool(recent_forms & {"20-F", "20-F/A", "40-F", "40-F/A"}) and "10-K" not in recent_forms
        return CompanyProfile(
            ticker=ticker.upper(),
            cik=cik,
            name=sub.get("name") or info.get("title"),
            sic_code=str(sub.get("sic") or "") or None,
            industry=sub.get("sicDescription"),
            sector=sub.get("category"),
            description=sub.get("description") or None,
            exchange=exchanges[0] if exchanges else None,
            shares_outstanding=self._shares_outstanding(cik),
            foreign_filer=foreign,
        )

    # -- companyfacts (XBRL) -------------------------------------------------
    def _companyfacts(self, cik: str) -> dict:
        # In-memory cache of the parsed 3.7MB facts so the several per-page
        # endpoints don't each re-read + re-parse it from disk (latency).
        cached = _FACTS_MEM.get(cik)
        if cached is not None:
            return cached

        def load():
            return get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", headers=_UA, provider=self.name)

        data = cache.get_or_set("edgar", f"facts:{cik}", ttl_seconds=7 * 86400, loader=load).value
        # Each parsed companyfacts is large (raw ~3.7MB, much bigger in RAM). Keep only a
        # few in memory at once — a universe-wide backtest touches hundreds of tickers, and
        # holding 40 parsed-facts blobs was a primary cause of 512MB OOM kills.
        if len(_FACTS_MEM) >= 4:
            _FACTS_MEM.clear()
        _FACTS_MEM[cik] = data
        return data

    def _shares_outstanding(self, cik: str) -> float | None:
        facts = self._companyfacts(cik).get("facts", {})
        entries = _entries(facts, ["EntityCommonStockSharesOutstanding"])
        latest = None
        for e in entries:
            if e.get("val") and e.get("end"):
                if latest is None or e["end"] > latest[0]:
                    latest = (e["end"], e["val"])
        return float(latest[1]) if latest else None

    # -- statements ----------------------------------------------------------
    # ``point_in_time=True`` returns the *originally filed* value for each period
    # (earliest filing wins) instead of the latest restatement, so each row's
    # filing_date is the date the figures first became public knowledge. That is
    # the correct view for backtests; the default (restated) view is correct for
    # current-state analysis in the UI.
    def get_income_statements(self, ticker: str, *, period: Period = Period.ANNUAL,
                              point_in_time: bool = False) -> list[IncomeStatement]:
        facts = self._companyfacts(self.resolve_cik(ticker)["cik"]).get("facts", {})
        rows = _build_periods(facts, INCOME_TAGS, period, instant=False, point_in_time=point_in_time)
        out: list[IncomeStatement] = []
        for key, data in rows.items():
            fy, p = key
            if data.get("gross_profit") is None and data.get("revenue") is not None and data.get("cost_of_revenue") is not None:
                data["gross_profit"] = data["revenue"] - data["cost_of_revenue"]
            out.append(IncomeStatement(fiscal_year=fy, period=p, source=self.name, **data))
        return _sorted(out)

    def get_balance_sheets(self, ticker: str, *, period: Period = Period.ANNUAL,
                           point_in_time: bool = False) -> list[BalanceSheet]:
        facts = self._companyfacts(self.resolve_cik(ticker)["cik"]).get("facts", {})
        rows = _build_periods(facts, BALANCE_TAGS, period, instant=True, point_in_time=point_in_time)
        out: list[BalanceSheet] = []
        for (fy, p), data in rows.items():
            st, lt = data.get("short_term_debt"), data.get("long_term_debt")
            if st is not None or lt is not None:
                data["total_debt"] = (st or 0) + (lt or 0)
            out.append(BalanceSheet(fiscal_year=fy, period=p, source=self.name, **data))
        return _sorted(out)

    def get_cash_flows(self, ticker: str, *, period: Period = Period.ANNUAL,
                       point_in_time: bool = False) -> list[CashFlowStatement]:
        facts = self._companyfacts(self.resolve_cik(ticker)["cik"]).get("facts", {})
        rows = _build_periods(facts, CASHFLOW_TAGS, period, instant=False, point_in_time=point_in_time)
        out: list[CashFlowStatement] = []
        for (fy, p), data in rows.items():
            ocf, capex = data.get("operating_cash_flow"), data.get("capital_expenditures")
            if ocf is not None and capex is not None:
                data["free_cash_flow"] = ocf - abs(capex)
            out.append(CashFlowStatement(fiscal_year=fy, period=p, source=self.name, **data))
        return _sorted(out)


    # -- filings / ownership -------------------------------------------------
    def _recent_filings(self, cik: str) -> list[dict]:
        def load():
            return get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=_UA, provider=self.name)

        sub = cache.get_or_set("edgar", f"submissions:{cik}", ttl_seconds=86400, loader=load).value
        rec = sub.get("filings", {}).get("recent", {})
        forms = rec.get("form", [])
        out = []
        for i in range(len(forms)):
            accn = rec["accessionNumber"][i]
            doc = rec["primaryDocument"][i] if i < len(rec.get("primaryDocument", [])) else ""
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}"
            out.append({
                "form": forms[i],
                "filing_date": rec["filingDate"][i],
                "report_date": (rec.get("reportDate") or [""] * len(forms))[i] or None,
                "accession_no": accn,
                "primary_document": doc,
                "items": (rec.get("items") or [""] * len(forms))[i] or None,
                "base": base,
                "primary_doc_url": f"{base}/{doc}" if doc else f"{base}/",
            })
        return out

    def get_filings(self, ticker: str, *, forms: list[str] | None = None, limit: int = 40) -> list[Filing]:
        cik = self.resolve_cik(ticker)["cik"]
        rows = self._recent_filings(cik)
        if forms:
            wanted = {f.upper() for f in forms}
            rows = [r for r in rows if r["form"].upper() in wanted]
        return [Filing(form_type=r["form"], filing_date=r["filing_date"], period_of_report=r["report_date"],
                       accession_no=r["accession_no"], primary_doc_url=r["primary_doc_url"], items=r["items"])
                for r in rows[:limit]]

    def get_large_stakes(self, ticker: str, *, limit: int = 30) -> list[LargeStake]:
        cik = self.resolve_cik(ticker)["cik"]
        out = []
        for r in self._recent_filings(cik):
            f = r["form"].upper()
            if "13D" in f or "13G" in f:
                out.append(LargeStake(form_type=r["form"], filing_date=r["filing_date"],
                                      accession_no=r["accession_no"], primary_doc_url=r["primary_doc_url"],
                                      intent="active" if "13D" in f else "passive"))
        return out[:limit]

    def get_insider_transactions(self, ticker: str, *, limit_filings: int = 30) -> list[InsiderTransaction]:
        cik = self.resolve_cik(ticker)["cik"]
        form4s = [r for r in self._recent_filings(cik) if r["form"] in ("4", "4/A")][:limit_filings]
        transactions: list[InsiderTransaction] = []
        for r in form4s:
            # primaryDocument is the XSL-rendered path (e.g. xslF345X06/form4.xml);
            # the raw XML is the basename in the filing directory.
            raw_name = r["primary_document"].split("/")[-1] if r["primary_document"] else "form4.xml"
            url = f"{r['base']}/{raw_name}"

            def load():
                return get_text(url, headers=_UA, provider=self.name)

            try:
                xml = cache.get_or_set("edgar", f"form4:{r['accession_no']}", ttl_seconds=30 * 86400, loader=load).value
                transactions.extend(_parse_form4(xml, accn=r["accession_no"], filing_url=r["primary_doc_url"]))
            except Exception:
                continue  # skip unparseable filing; never fail the whole request
        transactions.sort(key=lambda t: t.transaction_date or "", reverse=True)
        return transactions


# --- Form 4 parsing --------------------------------------------------------
def _text(node, path: str) -> str | None:
    el = node.find(path)
    return el.text.strip() if (el is not None and el.text) else None


def _num(node, path: str) -> float | None:
    v = _text(node, path)
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _parse_form4(xml_text: str, *, accn: str, filing_url: str) -> list[InsiderTransaction]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    owner = root.find("reportingOwner")
    name = title = relationship = None
    if owner is not None:
        name = _text(owner, "reportingOwnerId/rptOwnerName")
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            roles = []
            if _text(rel, "isDirector") in ("1", "true"):
                roles.append("Director")
            if _text(rel, "isOfficer") in ("1", "true"):
                roles.append("Officer")
            if _text(rel, "isTenPercentOwner") in ("1", "true"):
                roles.append("10% Owner")
            relationship = ", ".join(roles) or None
            title = _text(rel, "officerTitle")

    out: list[InsiderTransaction] = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(tx, "transactionCoding/transactionCode")
        shares = _num(tx, "transactionAmounts/transactionShares/value")
        price = _num(tx, "transactionAmounts/transactionPricePerShare/value")
        ad = _text(tx, "transactionAmounts/transactionAcquiredDisposedCode/value")
        out.append(InsiderTransaction(
            insider_name=name, insider_title=title, relationship=relationship,
            transaction_date=_text(tx, "transactionDate/value"),
            transaction_code=code,
            acquired_disposed=ad,
            shares=shares,
            price=price,
            value=(shares * price) if (shares is not None and price is not None) else None,
            shares_owned_after=_num(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
            is_open_market=code in OPEN_MARKET_CODES,
            filing_ref=accn,
            filing_url=filing_url,
        ))
    return out


# --- XBRL extraction helpers -----------------------------------------------
def _unit_entries(block_tag: dict) -> list[dict]:
    units = block_tag.get("units", {})
    for unit_key in ("USD", "USD/shares", "shares"):
        if unit_key in units:
            return units[unit_key]
    for v in units.values():
        return v
    return []


def _entries(facts: dict, tags: list[str]) -> list[dict]:
    """First present tag's entries (for single-concept lookups like shares outstanding)."""
    for ns in ("us-gaap", "dei"):
        block = facts.get(ns, {})
        for tag in tags:
            if tag in block:
                return _unit_entries(block[tag])
    return []


def _entries_by_priority(facts: dict, tags: list[str]) -> list[tuple[int, list[dict]]]:
    """All present candidate tags as ``(priority, entries)`` — lower priority wins.

    Companies change which tag they use over time (e.g. ``PaymentsOfDividendsCommonStock``
    -> ``PaymentsOfDividends``), so we consult every candidate and fill each period from
    the highest-priority tag that actually reports it (PRD 12 §9).
    """
    out: list[tuple[int, list[dict]]] = []
    for ns in ("us-gaap", "dei"):
        block = facts.get(ns, {})
        for prio, tag in enumerate(tags):
            if tag in block:
                entries = _unit_entries(block[tag])
                if entries:
                    out.append((prio, entries))
    return out


def _is_annual_flow(e: dict) -> bool:
    start, end = e.get("start"), e.get("end")
    if not start or not end:
        return False
    try:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return False
    return 350 <= days <= 380


def _is_quarter_flow(e: dict) -> bool:
    start, end = e.get("start"), e.get("end")
    if not start or not end:
        return False
    try:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return False
    return 80 <= days <= 100


def _period_key(e: dict, period: Period) -> tuple[int, str] | None:
    """Derive (fiscal_year, period_label). Uses the XBRL ``frame`` when available."""
    end = e.get("end")
    if not end:
        return None
    fy = int(end[:4])
    if period is Period.ANNUAL:
        return (fy, "FY")
    frame = e.get("frame", "") or ""
    if "Q" in frame:  # e.g. CY2023Q3
        try:
            yr = int(frame[2:6])
            q = frame[frame.index("Q"):][:2]
            return (yr, q)
        except (ValueError, IndexError):
            pass
    fp = e.get("fp", "")
    return (fy, fp if fp.startswith("Q") else f"Q@{end}")


def _build_periods(facts: dict, tag_map: dict[str, list[str]], period: Period, *, instant: bool,
                   point_in_time: bool = False) -> dict:
    """Return ``{(fiscal_year, period_label): {field: value}}`` for all fields.

    For each field we prefer the highest-priority tag (lowest index) that reports a
    given period. Within the same tag, the default prefers the most-recently-filed
    value (restated figures — right for current-state analysis), while
    ``point_in_time=True`` prefers the *earliest*-filed value (originally-reported
    figures with original filing dates — right for backtests, where using restated
    numbers or late comparative filing dates would leak future knowledge).
    """
    rows: dict[tuple[int, str], dict] = {}
    chosen: dict[tuple, tuple[int, str]] = {}  # (key, field) -> (priority, filed)

    for field, tags in tag_map.items():
        for priority, entries in _entries_by_priority(facts, tags):
            for e in entries:
                form = e.get("form", "")
                val = e.get("val")
                if val is None:
                    continue
                if period is Period.ANNUAL:
                    # 10-K (domestic) + 20-F / 40-F (foreign private issuers, e.g. ADRs like BABA, BIDU).
                    if not form.startswith(("10-K", "20-F", "40-F")):
                        continue
                    if not instant and not _is_annual_flow(e):
                        continue
                else:
                    if not form.startswith("10-Q"):
                        continue
                    if not instant and not _is_quarter_flow(e):
                        continue
                key = _period_key(e, period)
                if key is None:
                    continue
                marker_key = (key, field)
                filed = e.get("filed", "")
                prev = chosen.get(marker_key)
                if point_in_time:
                    # The earliest filing wins regardless of tag preference — it is what an
                    # investor actually knew first. (Companies switch tags over time, e.g.
                    # ASC-606 revenue: the preferred tag's first appearance is often a later
                    # comparative filing, and choosing it would hide the row for a year.)
                    # Tag priority only breaks ties within the same filing. Undated entries
                    # can't be gated, so they are skipped entirely.
                    if not filed:
                        continue
                    if prev is not None and (prev[1] < filed or (prev[1] == filed and prev[0] <= priority)):
                        continue
                else:
                    if prev is not None:
                        if prev[0] < priority:
                            continue  # a higher-priority tag already filled this field
                        if prev[0] == priority and filed < prev[1]:
                            continue  # same tag: keep the most recent restatement
                chosen[marker_key] = (priority, filed)
                row = rows.setdefault(key, {})
                row[field] = float(val)
                if e.get("filed"):
                    row["filing_date"] = e["filed"]
                if e.get("accn"):
                    row["filing_ref"] = e["accn"]
    if point_in_time:
        # A row becomes public knowledge when its statement was *originally* filed — the
        # earliest filing across its fields. Fields whose first tagged appearance is a
        # *later* filing (tag-scheme changes, restated comparatives) were not knowable
        # then, so they are dropped rather than allowed to either leak future data or
        # (via a max() gate) hide the whole row for a year.
        for key, row in rows.items():
            filed_dates = [chosen[(key, f)][1] for f in tag_map if (key, f) in chosen and chosen[(key, f)][1]]
            if not filed_dates:
                continue
            original = min(filed_dates)
            for f in tag_map:
                marker = (key, f)
                if marker in chosen and chosen[marker][1] > original:
                    row[f] = None
            row["filing_date"] = original
    return rows


def _sorted(items: list):
    return sorted(items, key=lambda s: (s.fiscal_year, s.period), reverse=True)
