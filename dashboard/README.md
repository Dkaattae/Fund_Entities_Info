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

`app.py` is the navigation shell (`st.navigation`) that registers all pages —
it has no content of its own; the first page below loads by default.

### 1. Recently Formed Funds
Newly emerging pooled investment funds from Form D filings — funds with no
prior filing history, first sale yet to occur, and no prior adviser link in
Form ADV. Backed by `newly_emerging_funds` (latest 500 filings).

- Sidebar filters: fund type, shared-connections bucket (0 / 1–10 / 10–30 / 30+)
- KPIs: funds shown, with linked adviser, with shared-person connections
- Click a row for filing details, exemption badges (3(c)(1), 3(c)(7), 506(b)/(c)),
  EDGAR links, related persons, and other funds sharing a related person

### 2. Service Provider Changes
SEC ERA advisers who changed auditor, custodian, fund administrator, prime
broker, or marketer between their two most recent filings. Backed by
`service_provider_changes`, `era_adviser_transitions`.

Tabs:
- **New Advisers** — adviser transition events (new SEC ERA, ERA → RIA,
  ERA withdrawn, new state ERA/RIA) with a transitions-by-quarter matrix
  and a filterable event list
- **Auditors / Custodians / Fund Admins / Prime Brokers / Marketers** — per
  provider type: who added, dropped, or swapped. Click a row for the full
  current-vs-prior provider detail and the adviser's funds.

Sidebar filters (provider tabs): change type, fiscal year end.

### 3. Fund Formation by Quarter
Count of initial (non-amendment) Form D filings for pooled investment funds,
2024 onward, broken down by fund type. Backed by
`form_d_new_funds_by_quarter` and `form_d_pooled_funds`.

- Stacked bar and per-type trend lines by quarter
- **Fund formation by state**: US choropleth + top-state tables (uses
  executive-officer/promoter state as fallback; WA is inflated by AngelList
  platform filings)
- **Platform / Syndicate funds** ("a series of" name matches) by quarter
- Sidebar filter: fund type

### 4. First Round Fundraise
For funds that have raised their first dollar (first filing where
`total_amount_sold > 0`, 2024 onward): how much, and how long it took from
the initial Form D. Backed by `form_d_first_raise`.

- Median raise and median days-to-raise by **adviser cohort** (ERA big/small,
  multi-state, single-state, no adviser), by fund type, and by investor
  exemption (3(c)(1) vs 3(c)(7))
- Scatter of raise amount vs days to raise, colored by cohort
- Click a row in the top-raises table for the detail panel
- Sidebar filters: US/non-US, shared-connections bucket, fund type,
  max days to first raise, exclude raises > $100M

### 5. Fund Closures
ERA closure signals: `fund_removed` (a fund dropped off Form ADV),
`aum_zeroed` (adviser AUM went from > 0 to 0), `adviser_terminated` (final
ERA report filed). Backed by `era_fund_closures`.

- KPIs per signal type + late-filer count; stacked closure-events-by-quarter chart
- Click a row for AUM before/after, IAPD and EDGAR links
- Sidebar filters: signal type, quarter, hide funds that changed adviser
  (default on), hide late filers (> 18-month gap)

### 6. Nothing Fund Tracker
Funds that started with $0 raised, no shared-person connections, and first
sale yet to occur — tracks fundraising velocity ($/day) by adviser cohort and
investor type. Backed by `form_d_nothing_fund_tracker`.

- Median velocity and % raised by cohort × investor type; cumulative
  fundraising-path lines (institutional vs individual); velocity-vs-raised scatter
- Sidebar filters: initial filing quarter (defaults exclude the two most
  recent, immature quarters), investor type, fund type, only-raised toggle

### 7. Newly Registered State RIAs
Investment advisers newly registered at the **state** level (not SEC ERA),
from the daily IA_FIRM_STATE feed. Backed by `newly_registered_rias` +
`ria_state_registrations`.

- AUM cohort distribution chart; registration list sorted by first
  registration date
- Click a row for AUM, employees, address/phone/website, IAPD link
- Sidebar filters: lookback (30/90/180 days/all), HQ state, status

### 8. Service Provider Directory
Year-over-year adviser count per service provider from ERA annual filings.
Backed by `service_provider_yoy` + `service_provider_dim`.

- One tab per provider type; each shows YoY KPIs (providers, adviser slots,
  growers, new entrants) and a top-N bar chart
- Tables split into registered (PCAOB # / SEC # / LEI / CRD #) vs
  no-registry-number providers, with per-type explanations; fund admins have
  no registry ID and get a single table
- Auditors tab: expander flagging funds that raised money while using a
  non-PCAOB auditor
- Sidebar filters: US/non-US, min advisers, top-N for chart

### 9. Auditor Watch
ERA advisers whose latest filing reports non-PCAOB (or non-inspected) fund
auditors — auditor-upgrade leads as AUM approaches SEC-registration
territory. Separately quarantines suspicious template clusters: many
advisers sharing one auditor and one identical AUM (scam-farm pattern, e.g.
the INDICATOR GLOBAL cluster of 98 filers all reporting exactly $80M).
Backed by `adviser_auditor_status`.

- KPIs: lead advisers, leads ≥ $150M, template-cluster filers, distinct
  non-PCAOB firms
- Lead table (click a row for auditor detail + IAPD link), suspicious
  template clusters, top non-PCAOB auditor firms
- Sidebar filters: auditor status, AUM bucket, hide template clusters
  (default on)

### 10. Missing ERA Filings
SEC ERA advisers past their annual amendment due date (fiscal year end +
90 days) with no filing for the current reporting year — presumed active and
delinquent; wind-downs via final report are excluded (see Fund Closures).
Backed by `adviser_filing_compliance`. Formerly the "Compliance Concerns"
tab on page 2.

- KPIs: advisers overdue, avg/max days overdue, total AUM overdue
- Detail table (click a row for adviser detail); overdue count by fiscal
  year end
- Sidebar filters: fiscal year end, state, min days overdue
