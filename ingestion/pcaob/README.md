# PCAOB ingestion

Loads the PCAOB registered-firms directory and firm-inspection-report metadata
into the BigQuery `pcaob` dataset. Purpose: validate the auditor PCAOB numbers
advisers self-report in Form ADV against the actual registry before trusting
them as identity — the custodian-LEI / prime-broker-BD pattern. See
project_plan.md "PCAOB Ingestion Plan (AUDITOR wiring)".

## Tables

| Table | Grain | Notes |
|---|---|---|
| `pcaob.registered_firms` | one row per firm_id (~4.1k) | COMPLETE directory incl. withdrawn/revoked firms: name, other/predecessor names, city/state/country, HQ address, registration status + date, audit-report activity, HFCAA flag. The identity-validation surface. |
| `pcaob.firm_inspections` | one row per published inspection report (~4.3k) | firm_id, report date/year, inspection type, network, Part I.A deficiency counts/rate, QC-criticism flag, report PDF URL. Auditor Watch enrichment; not identity. |

Both tables are fully replaced each load and carry a `load_ts` column stamped
at load time (dlt's pandas/arrow path adds no `_dlt_load_id`; the monthly
guard and dbt source freshness key off `load_ts`).

## Sources (chosen 2026-07-10 — see the decision gate in project_plan.md)

- **Registered firms**: the JSON search API behind
  [pcaobus.org/oversight/registration/registered-firms](https://pcaobus.org/oversight/registration/registered-firms)
  (Hawksearch, `Content Type = Firm`, ~43 paged requests of 96). Chosen over
  the official Form AP bulk CSV (`assets.pcaobus.org/firm-filings/FirmFilings.zip`)
  because Form AP covers only issuer-audit firms — it validates just 52% of
  the distinct PCAOB numbers reported in ERA filings vs 89.7% for the full
  directory (99.1% mention-weighted); the big misses were real private-fund
  auditors (PwC Channel Islands, KPMG Luxembourg, RSM Cayman…). The directory
  is a strict superset of both the Form AP firm list and the inspections list.
  The client GUID + endpoint are read from the page's `data-*` attributes and
  pinned in `pcaob_ingestion.py` — if the fetch breaks, re-inspect the page.
- **Inspections**: the official CSV download on
  [firm-inspection-reports](https://pcaobus.org/oversight/inspections/firm-inspection-reports)
  (UTF-16LE, no BOM).

## Running

```bash
python pcaob_ingestion.py   # fetch directory + inspections, replace both tables
```

Raw snapshots (directory JSON + inspections CSV, date-stamped) land in
`files/` (gitignored).

## Cadence

Monthly, via the `pcaob-monthly` flow (`orchestration/flows.py pcaob`,
GH Actions `pcaob-monthly.yml`, cron daily 2nd–8th 04:00 UTC with an in-flow
guard that no-ops once the month is loaded) — deliberately before
gleif-monthly (05:00) and era-monthly (06:00, window opens the 5th), so the
provider registry mints new AUDITOR rows against a fresh PCAOB list. A
refresh never churns existing `sp_` ids — the registry reads validation
results only at mint time. Freshness thresholds (warn 40d / error 55d) live
in `transform/sec_filings/models/staging/sources.yml`.
