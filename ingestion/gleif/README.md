# GLEIF LEI ingestion

Loads the [GLEIF golden copy](https://www.gleif.org/en/lei-data/gleif-golden-copy)
(Level 1 LEI records, ~3.4M entities, free) into the BigQuery `gleif` dataset.
Purpose: global entity identity for service-provider matching — a fund admin
name that matches an LEI record gets a stable `LEI:` identifier instead of a
content-derived `NAME:` hash, and non-US admins (Cayman, Lux, Ireland, Channel
Islands…) get covered without hand-curating seed rows. See project_plan.md
"Problem 3 — Non-US fund admins missing".

## Tables

| Table | Grain | Notes |
|---|---|---|
| `gleif.lei_records` | one row per LEI | legal name, legal/HQ city+region+country (ISO-2), jurisdiction, entity category/status, registration status + dates |
| `gleif.lei_names` | one row per (lei, name, name_type) | legal name + OtherEntityNames + transliterated variants; the matching surface for dbt |

## Running

```bash
python gleif_ingestion.py                 # download latest golden copy → load
python gleif_ingestion.py path/to/csv.zip # load an already-downloaded file
```

The download is ~470 MB (zip) and lands in `files/` (gitignored). Loading
replaces both tables in full.

## Cadence

Monthly, via the `gleif-monthly` flow (`orchestration/flows.py gleif`,
GH Actions `gleif-monthly.yml`, cron daily 2nd–8th 05:00 UTC with an in-flow
guard that no-ops once the month is loaded). Decided 2026-07-10; monthly over
quarterly so a refresh always lands just before `era-monthly` (window opens
the 5th) mints new provider-registry rows against the LEI match map. A
refresh never churns existing `sp_` ids — the registry reads the map only at
mint time. The flow reruns `tag:gleif` (both staging models +
`int_fund_admin_lei_map`) after each load, and freshness thresholds live in
`transform/sec_filings/models/staging/sources.yml` (warn 40d / error 55d).
Manual run: `python orchestration/flows.py gleif`, or this script directly
for an ad-hoc load outside the monthly window.

## Level 2 (parent relationships)

GLEIF also publishes relationship records (`rr` files) with direct/ultimate
parent links — useful later for the `parent_group` corporate-family rollup in
the crosswalk upgrade. Not ingested yet.
