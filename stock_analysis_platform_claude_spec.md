# Local Stock Analysis Platform — Codex Project Spec

## 1. Project Goal

Build a local web application for analyzing public stocks using free or low-cost APIs. The platform should display stock charts, trading volume, financial statements, free cash flow trends, valuation models, and fair value estimates.

The app should feel like a lightweight personal version of Koyfin, Finviz, or a stock research dashboard.

Primary goals:
- Pull financial statement data from free APIs.
- Pull historical stock price and volume data.
- Display clean financial charts.
- Calculate multiple intrinsic value estimates.
- Show bull/base/bear fair value ranges.
- Cache API data locally to avoid rate-limit issues.
- Keep the project modular so valuation models can be improved over time.

---

## 2. Recommended Tech Stack

### Frontend
- Next.js
- React
- TypeScript
- Tailwind CSS
- TradingView Lightweight Charts

### Backend
- FastAPI or Next.js API routes
- Python preferred for financial calculations
- PostgreSQL or SQLite for local development

### Data Storage
Start with SQLite locally. Move to PostgreSQL later if needed.

### Data Sources
Use a hybrid API approach:

#### Financial Statements / Fundamentals
- Financial Modeling Prep API
- Alpha Vantage
- SEC EDGAR API

#### Stock Prices / Volume
- Twelve Data
- Alpha Vantage
- Financial Modeling Prep
- Polygon if a paid tier is eventually needed

#### SEC Filings
- SEC EDGAR API

---

## 3. Core Features

### Stock Overview Page

Route:

```txt
/company/[ticker]
```

Display:
- Company name
- Ticker
- Sector
- Industry
- Market cap
- Current price
- Price change
- 52-week high/low
- P/E ratio
- Price/free cash flow
- EV/EBITDA
- Dividend yield if applicable
- Basic company description

---

### Price and Volume Charts

Display:
- Candlestick chart
- Daily/weekly/monthly toggle
- Volume bars
- Moving averages later if desired

Use TradingView Lightweight Charts.

Data needed:
- Date
- Open
- High
- Low
- Close
- Volume

---

### Financial Statement Pages

Routes:

```txt
/financials/[ticker]/income-statement
/financials/[ticker]/balance-sheet
/financials/[ticker]/cash-flow
```

Display annual and quarterly data.

Income statement:
- Revenue
- Gross profit
- Operating income
- Net income
- EPS
- Shares outstanding

Balance sheet:
- Cash
- Total assets
- Total liabilities
- Total debt
- Shareholder equity

Cash flow:
- Operating cash flow
- Capital expenditures
- Free cash flow
- Stock-based compensation
- Dividends paid
- Share repurchases

---

## 4. Valuation Module

Route:

```txt
/valuation/[ticker]
```

The valuation page should calculate multiple fair value estimates instead of relying on one formula.

Main output:

```txt
Current Price: $X
Bear Case Fair Value: $X
Base Case Fair Value: $X
Bull Case Fair Value: $X
Blended Fair Value: $X
Margin of Safety: X%
```

Formula:

```txt
Margin of Safety = (Fair Value - Current Price) / Fair Value
```

---

## 5. Valuation Models

### 5.1 Discounted Cash Flow Model

Use free cash flow as the core input.

Inputs:
- Current free cash flow
- FCF growth rate years 1–5
- FCF growth rate years 6–10
- Discount rate
- Terminal growth rate
- Net debt
- Shares outstanding

Formula:

```txt
Projected FCF = Prior Year FCF × (1 + Growth Rate)

Present Value of FCF = Projected FCF / (1 + Discount Rate)^Year

Terminal Value = Final Year FCF × (1 + Terminal Growth Rate) / (Discount Rate - Terminal Growth Rate)

Enterprise Value = Sum of PV FCF + PV Terminal Value

Equity Value = Enterprise Value - Net Debt

Fair Value Per Share = Equity Value / Shares Outstanding
```

Scenarios:
- Bear: lower growth, higher discount rate, lower terminal growth
- Base: reasonable assumptions
- Bull: higher growth, lower discount rate, higher terminal growth

---

### 5.2 Owner Earnings Model

Buffett-style intrinsic value model.

Formula:

```txt
Owner Earnings =
Net Income
+ Depreciation & Amortization
- Maintenance CapEx
± Changes in Working Capital
```

Since maintenance CapEx is hard to know, estimate it using one of:
- Average CapEx as percentage of revenue
- Depreciation & amortization as proxy
- User-defined percentage of total CapEx

Then discount owner earnings like a DCF.

Inputs:
- Net income
- D&A
- CapEx
- Working capital changes
- Growth rate
- Discount rate
- Terminal growth rate
- Shares outstanding
- Net debt

---

### 5.3 Earnings Multiple Valuation

Useful for profitable companies.

Inputs:
- Current EPS
- Expected EPS growth
- Projection period
- Fair exit P/E multiple
- Discount rate

Formula:

```txt
Future EPS = Current EPS × (1 + EPS Growth Rate)^Years

Future Share Price = Future EPS × Fair P/E Multiple

Present Fair Value = Future Share Price / (1 + Discount Rate)^Years
```

Scenarios:
- Bear: low EPS growth, compressed P/E
- Base: normal EPS growth, average P/E
- Bull: strong EPS growth, premium P/E

---

### 5.4 Revenue Multiple Valuation

Useful for growth companies or companies with temporarily depressed earnings.

Inputs:
- Revenue
- Revenue growth rate
- Projection years
- Fair EV/Sales multiple
- Net debt
- Shares outstanding
- Discount rate

Formula:

```txt
Future Revenue = Revenue × (1 + Revenue Growth Rate)^Years

Future Enterprise Value = Future Revenue × Fair EV/Sales Multiple

Future Equity Value = Future Enterprise Value - Net Debt

Future Share Price = Future Equity Value / Shares Outstanding

Present Fair Value = Future Share Price / (1 + Discount Rate)^Years
```

---

### 5.5 EBITDA Multiple Valuation

Useful for mature businesses.

Inputs:
- EBITDA
- EBITDA growth rate
- Projection years
- Fair EV/EBITDA multiple
- Net debt
- Shares outstanding
- Discount rate

Formula:

```txt
Future EBITDA = EBITDA × (1 + EBITDA Growth Rate)^Years

Future Enterprise Value = Future EBITDA × Fair EV/EBITDA Multiple

Future Equity Value = Future Enterprise Value - Net Debt

Future Share Price = Future Equity Value / Shares Outstanding

Present Fair Value = Future Share Price / (1 + Discount Rate)^Years
```

---

### 5.6 Dividend Discount Model

Only use if the company pays a consistent dividend.

Inputs:
- Current annual dividend per share
- Dividend growth rate
- Required return

Formula:

```txt
Fair Value = Next Year Dividend / (Required Return - Dividend Growth Rate)
```

Where:

```txt
Next Year Dividend = Current Dividend × (1 + Dividend Growth Rate)
```

Only valid when required return is greater than dividend growth rate.

---

### 5.7 Peer Comparable Valuation

Compare the company against similar companies.

Metrics:
- P/E
- Forward P/E
- EV/Sales
- EV/EBITDA
- Price/FCF
- PEG ratio

Formula:

```txt
Implied Fair Value = Company Metric × Peer Median Multiple
```

Examples:

```txt
EPS × Peer Median P/E = Fair Value Per Share

Revenue × Peer Median EV/Sales = Implied Enterprise Value

EBITDA × Peer Median EV/EBITDA = Implied Enterprise Value
```

Then:

```txt
Equity Value = Enterprise Value - Net Debt

Fair Value Per Share = Equity Value / Shares Outstanding
```

---

## 6. Blended Fair Value

Do not present one valuation as absolute truth.

Calculate a weighted fair value:

```txt
Blended Fair Value =
DCF Value × 35%
+ Owner Earnings Value × 20%
+ Earnings Multiple Value × 20%
+ EBITDA Multiple Value × 15%
+ Revenue Multiple Value × 10%
```

Weights should be adjustable.

For unprofitable companies:
- Reduce DCF/earnings weights.
- Increase revenue multiple weight.

For dividend companies:
- Include dividend discount model.

For banks/financials:
- Avoid EBITDA and standard FCF models.
- Use book value, tangible book value, ROE, and P/E instead.

---

## 7. Database Schema

### companies

```sql
CREATE TABLE companies (
  id INTEGER PRIMARY KEY,
  ticker TEXT UNIQUE NOT NULL,
  name TEXT,
  sector TEXT,
  industry TEXT,
  description TEXT,
  exchange TEXT,
  currency TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### price_history

```sql
CREATE TABLE price_history (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  date DATE NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  adjusted_close REAL,
  volume INTEGER,
  UNIQUE(ticker, date)
);
```

### income_statements

```sql
CREATE TABLE income_statements (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  fiscal_year INTEGER,
  period TEXT,
  revenue REAL,
  gross_profit REAL,
  operating_income REAL,
  net_income REAL,
  eps REAL,
  weighted_average_shares REAL,
  filing_date DATE,
  UNIQUE(ticker, fiscal_year, period)
);
```

### balance_sheets

```sql
CREATE TABLE balance_sheets (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  fiscal_year INTEGER,
  period TEXT,
  cash_and_equivalents REAL,
  total_assets REAL,
  total_liabilities REAL,
  total_debt REAL,
  shareholder_equity REAL,
  filing_date DATE,
  UNIQUE(ticker, fiscal_year, period)
);
```

### cash_flow_statements

```sql
CREATE TABLE cash_flow_statements (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  fiscal_year INTEGER,
  period TEXT,
  operating_cash_flow REAL,
  capital_expenditures REAL,
  free_cash_flow REAL,
  depreciation_and_amortization REAL,
  stock_based_compensation REAL,
  dividends_paid REAL,
  share_repurchases REAL,
  filing_date DATE,
  UNIQUE(ticker, fiscal_year, period)
);
```

### valuation_results

```sql
CREATE TABLE valuation_results (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  valuation_date DATE NOT NULL,
  current_price REAL,
  dcf_value REAL,
  owner_earnings_value REAL,
  earnings_multiple_value REAL,
  revenue_multiple_value REAL,
  ebitda_multiple_value REAL,
  dividend_discount_value REAL,
  peer_comps_value REAL,
  blended_fair_value REAL,
  bear_case_value REAL,
  base_case_value REAL,
  bull_case_value REAL,
  margin_of_safety REAL,
  assumptions_json TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. Backend Services

Suggested structure:

```txt
/backend
  /app
    /api
      company_routes.py
      price_routes.py
      financial_routes.py
      valuation_routes.py
    /services
      fmp_client.py
      alpha_vantage_client.py
      twelve_data_client.py
      sec_client.py
      valuation_engine.py
      cache_service.py
    /models
      company.py
      financial_statement.py
      price_history.py
      valuation.py
    /utils
      normalization.py
      financial_math.py
      validation.py
```

---

## 9. Frontend Structure

Suggested structure:

```txt
/frontend
  /app
    /company/[ticker]/page.tsx
    /valuation/[ticker]/page.tsx
    /financials/[ticker]/page.tsx
  /components
    StockChart.tsx
    VolumeChart.tsx
    FinancialTable.tsx
    ValuationSummary.tsx
    ScenarioInputs.tsx
    FairValueRange.tsx
    MetricCard.tsx
  /lib
    api.ts
    formatters.ts
    valuation.ts
```

---

## 10. API Routes

### Company

```txt
GET /api/company/{ticker}
```

Returns company profile and key metrics.

### Price History

```txt
GET /api/prices/{ticker}?range=1y&interval=1d
```

Returns OHLCV data.

### Financial Statements

```txt
GET /api/financials/{ticker}/income
GET /api/financials/{ticker}/balance-sheet
GET /api/financials/{ticker}/cash-flow
```

### Valuation

```txt
GET /api/valuation/{ticker}
POST /api/valuation/{ticker}
```

GET returns default valuation.

POST accepts custom assumptions:

```json
{
  "growth_rate_1_5": 0.08,
  "growth_rate_6_10": 0.04,
  "discount_rate": 0.10,
  "terminal_growth_rate": 0.025,
  "fair_pe": 22,
  "fair_ev_ebitda": 14,
  "fair_ev_sales": 6
}
```

---

## 11. Important Design Principles

- Do not rely on one API.
- Cache API responses locally.
- Keep valuation formulas transparent.
- Let users edit assumptions.
- Show valuation ranges, not fake precision.
- Clearly label assumptions.
- Separate raw data from calculated metrics.
- Store historical valuation results so assumptions can be compared over time.
- Do not treat API data as perfect. Validate and normalize everything.

---

## 12. Implementation Phases

### Phase 1 — MVP

Build:
- Ticker search
- Company profile
- Historical price chart
- Volume chart
- Cash flow statement
- Free cash flow chart
- Simple DCF calculator

### Phase 2 — Valuation Engine

Add:
- Bull/base/bear scenarios
- Owner earnings model
- Earnings multiple model
- Revenue multiple model
- EBITDA multiple model
- Blended fair value
- Margin of safety

### Phase 3 — Financial Dashboard

Add:
- Income statement charts
- Balance sheet charts
- Debt trends
- Margin trends
- Revenue growth
- FCF growth
- ROIC if data available

### Phase 4 — Peer Comparisons

Add:
- Peer group selection
- Peer median multiples
- Relative valuation
- Sector comparison

### Phase 5 — Watchlists

Add:
- Watchlist table
- Current price
- Fair value estimate
- Upside/downside
- Margin of safety
- Last updated date

---

## 13. First Codex Prompt

Use this prompt to start implementation:

```txt
We are building a local stock analysis platform using the attached project spec.

Start by creating the initial project structure for a Next.js frontend and Python FastAPI backend.

Implement:
1. A backend health check route.
2. A basic company profile endpoint using placeholder data.
3. A frontend company page at /company/[ticker].
4. A reusable MetricCard component.
5. A placeholder valuation summary component.

Follow clean architecture principles. Keep API clients, services, models, and routes separate. Do not hardcode logic into frontend components if it belongs in the backend.
```

---

## 14. Second Codex Prompt

After the skeleton is created:

```txt
Implement the valuation engine described in the project spec.

Create pure Python functions for:
1. DCF valuation
2. Owner earnings valuation
3. Earnings multiple valuation
4. Revenue multiple valuation
5. EBITDA multiple valuation
6. Dividend discount valuation
7. Blended fair value calculation
8. Margin of safety calculation

Add unit tests for each model.

The functions should accept explicit input parameters and return structured dictionaries with assumptions, intermediate values, and final fair value per share.
```

---

## 15. Notes

This project should be built as a personal investing research tool, not as financial advice. All fair value estimates should be presented as model outputs based on assumptions.
