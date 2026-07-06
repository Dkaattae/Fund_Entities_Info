# ADV Form Pipeline

SEC Form ADV bulk data pipeline. Downloads monthly CSV archives from EDGAR and loads into BigQuery. Covers RIA (Registered Investment Advisers), ERA (Exempt Reporting Advisers), and State-Level Registered Investment Advisers.

## Data Sources

- **SEC IAPD (Investment Adviser Public Disclosure)** - monthly bulk ZIP archives containing CSV files
  - URL pattern: `https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/{year}/ADV_Filing_Data_{date}.zip`
- **SEC IA_FIRM_STATE Feed** - daily XML snapshots of state-registered investment advisers
  - URL pattern: `https://reports.adviserinfo.sec.gov/reports/CompilationReports/IA_FIRM_STATE_Feed_{mm}_{dd}_{yyyy}.xml.gz`

## Architecture

Downloads monthly ZIP archives from SEC, extracts CSV files, cleans data (encoding fixes, type coercion, special character removal), and loads into BigQuery via dlt with merge disposition.

```
RIA/ERA:          SEC IAPD monthly ZIP -> extract CSVs -> clean/normalize -> dlt -> BigQuery
State Advisers:   SEC daily XML feed -> download/parse -> raw tables + master table -> BigQuery
```

Three separate pipelines (RIA, ERA, State Adviser), each with their own BigQuery dataset and table naming.

## Files

| File | Description |
|---|---|
| `ria_ingestion.py` | RIA (Registered Investment Adviser) pipeline - code ready, not yet in use (see Status) |
| `era_ingestion.py` | ERA (Exempt Reporting Adviser) pipeline - backfill + monthly incremental |
| `util.py` | Shared utilities: URL builder, date helpers, string cleaning |
| `debug_script.py` | Development/testing script (PostgreSQL target, subset of tables) |
| `state_adviser_ingest.py` | State-level adviser pipeline - daily update + backfill + master table |
| `state_adviser_download.py` | Downloads daily XML snapshots from SEC IA_FIRM_STATE feed |
| `state_adviser_parse.py` | Parses XML into firms and registrations DataFrames |
| `run_all.py` | Runs all three pipelines together (incremental or backfill) |
| `wipe_dlt.py` | Utility to reset dlt pipeline state |

## BigQuery Datasets

- `ria_adv` - Registered Investment Adviser data
- `era_adv` - Exempt Reporting Adviser data
- `state_adviser` - State-level registered adviser data

## Tables (14 CSVs per dataset)

| Table | Description |
|---|---|
| `Base` / `BaseTable` | Core adviser entity (name, CRD, status, AUM) |
| `Ownership` / `OwnershipTable` | Ownership and control persons |
| `Address` / `AddressTable` | Adviser addresses |
| `Website` / `WebsiteTable` | Adviser websites |
| `Affiliations` / `AffiliationsTable` | Affiliated entities |
| `Funds` / `FundsTable` | Private funds managed (Schedule D, Sec 7.B) |
| `BrokerDealers` / `BrokerDealersTable` | Related broker-dealer entities |
| `Custodians` / `CustodiansTable` | Asset custody information |
| `Auditors` / `AuditorsTable` | Audit firms servicing the funds |
| `PrivateFundReporting` | Private fund reporting details |
| `CivilDisclosure` / `CivilDisclosureTable` | Civil disclosure events |
| `FilingTypes` / `FilingTypesTable` | Filing type metadata |
| `TypeOfClient` / `TypeOfClientTable` | Client type breakdown |
| `CompPractice` / `CompPracticeTable` | Compensation practices |

## State Adviser Tables

| Table | Description |
|---|---|
| `state_adviser_firms_raw` | Raw daily snapshot of firm records |
| `state_adviser_registrations_raw` | Raw daily snapshot of state/ERA registrations |
| `state_adviser_master` | Temporal master table tracking firm status (New/Active/Withdrawn) over time |

## Usage

```bash
# Run all pipelines together (incremental updates)
python run_all.py

# Run all pipelines together (full backfill)
python run_all.py --backfill

# RIA backfill (12 months)
python ria_ingestion.py

# ERA backfill (3 months) or monthly update
python era_ingestion.py

# State adviser daily update
python state_adviser_ingest.py
```

## Environment Variables

- `BIGQUERY_SERVICE_ACCOUNT_JSON` - GCP service account JSON string

## Status

- RIA: **code ready but never run** — no RIA data has been pulled yet. The
  pipeline mirrors ERA (same SEC ZIPs, IA_* files instead of ERA_*). Future
  plan: refactor the ERA ingestion code into one shared module with an
  ERA/RIA flag, then start loading RIA through it (see project_plan.md).
  Until that refactor, leave `ria_ingestion.py` as-is.
- ERA backfill + monthly update: working
- State adviser daily update + backfill + master merge: working (snapshot
  files older than 30 days are purged automatically on each daily run)
