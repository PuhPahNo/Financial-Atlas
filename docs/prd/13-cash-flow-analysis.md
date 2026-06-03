# 13 — Cash Flow Analysis

> Parent: [00-master-prd.md](00-master-prd.md) · The module the user specifically called out. Metric
> definitions are canonical in the [Glossary](00-master-prd.md#7-glossary); this PRD specifies the
> dedicated analytics view built on top of the cash-flow statement.

## 1. Purpose / why

Free cash flow and how a company deploys it (capex, buybacks, dividends, debt paydown) are the heart
of value investing. This module turns the raw cash-flow statement into the trends and quality ratios
an analyst actually reasons about, with full transparency on how each is computed.

## 2. User stories & acceptance criteria

- *As a value investor,* I see FCF and its drivers trended over years/quarters. **AC:** OCF, CapEx,
  and FCF render as trends with YoY change.
- *As a value investor,* I assess FCF quality and capital allocation. **AC:** FCF Margin %, FCF
  Conversion %, FCF per Share, CapEx as % of Revenue, buybacks, dividends, and net debt
  issuance/repayment are all displayed and trended.
- *As a user,* I trust the numbers. **AC:** each derived metric is labeled derived, with its inputs
  viewable ([03 derived_metrics.inputs_json](03-data-model.md)).

## 3. Scope (in / out)

### In scope — the metric set (exactly the user's list + supporting metrics)
| Metric | Formula | Source |
| --- | --- | --- |
| Operating Cash Flow trend | reported OCF over periods | raw |
| CapEx trend | reported capital expenditures over periods | raw |
| Free Cash Flow trend | `OCF − |CapEx|` (or reported FCF if present) | derived/raw |
| **FCF Margin %** | `FCF / Revenue` | derived |
| **FCF Conversion %** | `FCF / Net Income` | derived |
| Buybacks | reported share repurchases over periods | raw |
| Dividends | reported dividends paid over periods | raw |
| Debt issuance / repayment | `debt_issued`, `debt_repaid`, and net = issued − repaid | raw/derived |
| **FCF per Share** | `FCF / diluted weighted-avg shares` | derived |
| **CapEx as % of Revenue** | `|CapEx| / Revenue` | derived |

### Supporting metrics (not-limited-to, adds analytical depth)
- **Total capital returned** = buybacks + dividends; **payout vs FCF** = capital returned / FCF.
- **FCF growth** (YoY/CAGR); **cumulative FCF** over the window.
- **SBC as % of OCF** (cash-quality flag); **net debt change** (links to [03](03-data-model.md) balance data).
- **Reinvestment rate** = |CapEx| / OCF.

### Out of scope
- Valuation that consumes FCF lives in [14](14-valuation-engine.md) (this module feeds it).

## 4. Data requirements & sources

- Endpoint: `GET /api/v1/financials/{ticker}/cash-flow-analysis?period=` returning raw cash-flow lines
  + the derived metric series ([04](04-api-contract.md)).
- Inputs: `cash_flow_statements` + `income_statements` (revenue, net income, diluted shares) from
  EDGAR XBRL ([03](03-data-model.md)); derived values stored in `derived_metrics`.

## 5. Contracts

- Response: `{ periods:[...], raw:{ocf[],capex[],buybacks[],dividends[],debt_issued[],debt_repaid[]},
  derived:{fcf[],fcf_margin[],fcf_conversion[],fcf_per_share[],capex_pct_revenue[], ...}, currency }`.
- **Preconditions:** statements exist for ≥1 period; required inputs present per metric (else that
  metric is `null` for that period, with reason).
- **Postconditions:** sign convention consistent (CapEx magnitude positive in displays; cash outflows
  for buybacks/dividends shown as positive "returned" amounts with clear labeling); every derived value
  reproducible from `inputs_json`.
- **Invariant:** `FCF = OCF − |CapEx|` holds for every period unless an as-reported FCF overrides it
  (then both are shown).

## 6. UI/UX

- A grid of `TrendChart`s (one per metric family) + a `FinancialTable` with all metrics by period and
  the raw/derived badge ([06](06-design-system-ui.md)).
- A **capital allocation** stacked view: per period, how FCF was split across buybacks / dividends /
  debt paydown / retained.
- Toggle annual/quarter/TTM; CSV export; tooltips show the formula + inputs for each derived metric.

## 7. Business logic & edge cases

- **Negative FCF** (heavy investment / unprofitable) → margins/conversion can be negative or N/M;
  display "N/M" when denominator ≤ 0 (e.g. FCF Conversion when net income ≤ 0), never a misleading %.
- **Buybacks/dividends sign:** statements report these as negative cash flows; normalize to positive
  "capital returned" for display, documented in the normalization layer.
- **Debt issuance/repayment:** some filers net these; if only a net line exists, show net and flag it.
- **FCF Conversion > 100%** is meaningful (cash exceeds accounting profit) — not capped.
- Maintenance vs growth capex split is **not** in raw data → only the Owner Earnings model estimates
  it ([14](14-valuation-engine.md)); this module uses total capex.

## 8. Dependencies

[12](12-financial-statements.md) (statement data), [03](03-data-model.md) (derived_metrics),
[04](04-api-contract.md), [06](06-design-system-ui.md), [14](14-valuation-engine.md) (consumer of FCF).

## 9. Error handling

- Missing revenue/net income/shares for a period → corresponding ratio `null` with reason string;
  trend renders a gap, not a zero.

## 10. Testing requirements

- Unit tests for every derived metric vs hand-computed values, incl. negative-FCF and zero-denominator
  cases (must yield N/M, not crash or mislead).
- Sign-normalization tests (buybacks/dividends/debt) against real EDGAR cash-flow data.
- Invariant test: `FCF == OCF − |CapEx|` across fixtures; reproducibility test from `inputs_json`.

## 11. Open questions & assumptions

- FCF definition fixed to `OCF − CapEx` (Glossary). A "FCF incl. SBC adjustment" variant could be a
  toggle later; **assume** standard definition for v1.

## 12. Done criteria

- All listed metrics + supporting ratios render and trend (annual/quarter/TTM) from EDGAR data, each
  derived value labeled and reproducible, capital-allocation view working.
