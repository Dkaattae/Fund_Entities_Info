# ADV Form Pipeline

SEC Form ADV bulk data pipeline. Downloads monthly CSV archives from EDGAR and loads into BigQuery. Covers both RIA (Registered Investment Advisers) and ERA (Exempt Reporting Advisers).

## Data Source

- **SEC IAPD (Investment Adviser Public Disclosure)** - monthly bulk ZIP archives containing CSV files
- URL pattern: `https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/{year}/ADV_Filing_Data_{date}.zip`

## Architecture

Downloads monthly ZIP archives from SEC, extracts CSV files, cleans data (encoding fixes, type coercion, special character removal), and loads into BigQuery via dlt with merge disposition.

```
SEC IAPD monthly ZIP -> extract CSVs -> clean/normalize -> dlt -> BigQuery
```

Two separate pipelines for RIA and ERA, each with their own BigQuery dataset and table naming.

## Files

| File | Description |
|---|---|
| `ria_ingestion.py` | RIA (Registered Investment Adviser) pipeline - 12 month backfill |
| `era_ingestion.py` | ERA (Exempt Reporting Adviser) pipeline - backfill + monthly incremental |
| `util.py` | Shared utilities: URL builder, date helpers, string cleaning |
| `debug_script.py` | Development/testing script (PostgreSQL target, subset of tables) |
| `wipe_dlt.py` | Utility to reset dlt pipeline state |

## BigQuery Datasets

- `ria_adv` - Registered Investment Adviser data
- `era_adv` - Exempt Reporting Adviser data

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

## Usage

```bash
# RIA backfill (12 months)
python ria_ingestion.py

# ERA backfill (3 months) or monthly update
python era_ingestion.py
```

## Environment Variables

- `BIGQUERY_SERVICE_ACCOUNT_JSON` - GCP service account JSON string

## Status

- RIA backfill: working
- ERA backfill + monthly update: working
