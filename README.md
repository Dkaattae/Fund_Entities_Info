# Fund Entities Info

Regulatory intelligence platform for SEC-registered investment advisers and private funds. Ingests Form ADV, Form D, and broker-dealer data from SEC EDGAR, transforms it through a dbt semantic layer, and surfaces it in an interactive Streamlit dashboard.

**Live dashboard:** [https://fundentitiesinfo-foubiwtqd42c8dfehfjifa.streamlit.app](https://fundentitiesinfo-foubiwtqd42c8dfehfjifa.streamlit.app)

---

## Architecture

```
SEC EDGAR / IAPD
      │
      ▼
ingestion/          ← dlt pipelines (Python)
  adv-form/         ← Form ADV: RIA, ERA, State advisers
  form-d/           ← Form D: historical backfill + daily XML
  broker-dealer/    ← FOCUS reports + EDGAR filings
      │
      ▼
BigQuery (raw datasets)
  ria_adv / era_adv / state_adviser / form_d_filings / formd_filings_crawler
      │
      ▼
transform/sec_filings/   ← dbt (staging → intermediate → marts)
      │
      ▼
BigQuery (mart tables)
      │
      ▼
dashboard/          ← Streamlit app (8 pages)
```

Orchestration is handled by **Prefect** (`orchestration/`), which schedules daily and monthly pipeline runs.

---

## Repository Layout

| Path | Purpose |
|---|---|
| `ingestion/adv-form/` | Form ADV pipelines (RIA, ERA, State) |
| `ingestion/form-d/` | Form D historical backfill + daily crawler |
| `ingestion/broker-dealer/` | Broker-dealer FOCUS report pipeline |
| `ingestion/CIK/` | SEC CIK lookup reference |
| `transform/sec_filings/` | dbt project — staging / intermediate / marts |
| `orchestration/` | Prefect flows and deployment config |
| `dashboard/` | Streamlit multi-page app backed by BigQuery |
| `DomainModel.yml` | Canonical domain model (entities, relationships, time rules) |

---

## Data Sources

| Source | Format | Cadence | BigQuery Dataset |
|---|---|---|---|
| SEC IAPD — RIA | Monthly bulk ZIP / CSV | Monthly | `ria_adv` |
| SEC IAPD — ERA | Monthly bulk ZIP / CSV | Monthly | `era_adv` |
| SEC IA_FIRM_STATE feed | Daily XML | Daily | `state_adviser` |
| SEC EDGAR Form D bulk | Quarterly ZIP / TSV | Quarterly | `form_d_filings` |
| SEC EDGAR Form D daily | Daily index + per-filing XML | Daily | `formd_filings_crawler` |
| SEC Broker-Dealer FOCUS | Monthly TXT | Monthly | _(csv / BQ)_ |

---

## Transform (dbt)

Three-layer dbt project under `transform/sec_filings/`:

| Layer | Path | Description |
|---|---|---|
| Staging | `models/staging/` | Raw-to-typed casts for ERA, Form D, State ADV sources |
| Intermediate | `models/intermediate/` | Identity resolution, service-provider canonicalization, adviser–fund links |
| Marts | `models/marts/` | Query-ready tables consumed by the dashboard |

Domain model and identity-resolution rules are documented in [`DomainModel.yml`](DomainModel.yml).

---

## Dashboard Pages

The Streamlit app has 8 pages:

| Page | Description |
|---|---|
| 1. Recently Formed Funds | New pooled investment fund filings (Form D) with no prior adviser history |
| 2. Service Provider Changes | ERA advisers who changed auditor, custodian, fund admin, prime broker, or marketer between filings |
| 3. Fund Formation by Quarter | Count of new Form D filings by quarter and fund type since 2025-Q1 |
| 4. First Round Fundraise | First-dollar raises — amount, time-to-raise, adviser cohort, and exemption breakdown |
| 5. Fund Closures | Funds that have ceased operations based on Form ADV and Form D data |
| 6. Nothing Fund Tracker | Funds with no offering activity or service-provider relationships |
| 7. Newly Registered State RIAs | New state-level registered investment advisers from the daily feed |
| 8. Service Provider Directory | Canonical service provider reference with identity-resolution metadata |

See [`dashboard/README.md`](dashboard/README.md) for setup and run instructions.

---

## Setup

### Requirements

- Python 3.11+
- `BIGQUERY_SERVICE_ACCOUNT_JSON` — GCP service account key as a JSON string (set in environment, never committed to the repo)

### Install

Each subdirectory has its own `requirements.txt`. For the dashboard:

```bash
cd dashboard
pip install -r requirements.txt
```

### Run the dashboard locally

```bash
cd dashboard
streamlit run app.py
```

### Run ingestion pipelines

```bash
# All ADV pipelines (incremental)
cd ingestion/adv-form
python run_all.py

# Form D daily update
cd ingestion/form-d
python form_d_crawler.py
python form_d_detail.py
```

### Run dbt transforms

```bash
cd transform/sec_filings
dbt run
```

---

## Planned Features

- **Service provider bundle recommendation** — suggest providers based on peer relationships
- **Chatbot** — natural-language queries translated to SQL via the domain ontology
- **Knowledge graph** — service provider network in Neo4j
- **PCAOB auditor enrichment** — match auditors to PCAOB registration data
- **Missing ERA filing alerts** — compliance monitoring for overdue annual amendments

---

## License

See [LICENSE](LICENSE).
