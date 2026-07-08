# Fund Entities Dashboard

Streamlit dashboard backed by BigQuery. Covers SEC ERA (Form ADV) filings and Form D pooled investment fund filings.

## Requirements

- Python 3.11+
- `BIGQUERY_SERVICE_ACCOUNT_JSON` environment variable containing the BigQuery service account key as a JSON string

## Setup

Install dependencies from the dashboard directory:

```bash
cd dashboard
pip install -r requirements.txt
```

## Running

```bash
cd dashboard
streamlit run app.py
```

The app opens at **http://localhost:8501**. In GitHub Codespaces, port 8501 is auto-forwarded — open it from the **Ports** tab.

To run headlessly (e.g. in a Codespace or CI):

```bash
streamlit run app.py --server.port 8501 --server.headless true
```

## Pages

### 1. Recently Formed Funds (`app.py`)
Newly emerging pooled investment funds from Form D filings — funds with no prior filing history, first sale yet to occur, and no prior adviser link in Form ADV. Click any row to see:
- Filing details, fund type, exemptions claimed
- Linked adviser and their ERA relationship
- Related persons on the filing
- Other funds sharing a related person

### 2. Service Provider Changes
SEC ERA advisers who changed auditor, custodian, fund administrator, prime broker, or marketer between their two most recent filings.

Tabs:
- **New Advisers** — first-time ERA filers in the current reporting year
- **Compliance Concerns** — advisers past their annual amendment due date with no filing on record
- **Auditors / Custodians / Fund Admins / Prime Brokers / Marketers** — per provider type: who added, dropped, or swapped. Click a row to see the full current vs prior provider detail.

### 3. Fund Formation by Quarter
Count of initial (non-amendment) Form D filings for pooled investment funds since 2025-Q1, broken down by fund type (Hedge Fund, Private Equity, Venture Capital, Real Estate, Other).

- Stacked bar chart by quarter and fund type
- Trend lines per fund type
- Sidebar filter to select specific fund types

### 4. First Round Fundraise
For funds that have raised their first dollar (first filing where `total_amount_sold > 0`), shows:
- How much they raised and how long it took from their initial Form D filing
- Breakdown by **adviser cohort**: ERA big/small, multi-state big/small, single-state big/small, no adviser
- Breakdown by fund type and investor exemption (3(c)(1) vs 3(c)(7))
- Scatter plot of raise amount vs days to raise, colored by cohort
- Click any row in the top-raises table for a full detail panel

Sidebar filters: quarter, fund type, max days to first raise.

### 9. Auditor Watch
ERA advisers whose latest filing reports non-PCAOB (or non-inspected) fund
auditors — auditor-upgrade leads as AUM approaches SEC-registration
territory. Separately surfaces suspicious template clusters: many advisers
sharing one auditor and one identical AUM (scam-farm pattern, e.g. the
INDICATOR GLOBAL cluster of 98 filers all reporting exactly $80M).
Backed by `sec_filings_marts.adviser_auditor_status`.

*(Pages 5–8 exist but are not yet documented here — see `pages/`.)*
