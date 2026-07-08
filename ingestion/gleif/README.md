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

Manual / on-demand — no schedule. LEI records change slowly and the matching
layer only needs a reasonably current snapshot. Re-run before re-tuning
fund-admin matching. If this ever gets a schedule, add a freshness block to
`transform/sec_filings/models/staging/sources.yml` (the `gleif` source is
declared there without one, deliberately).

## Level 2 (parent relationships)

GLEIF also publishes relationship records (`rr` files) with direct/ultimate
parent links — useful later for the `parent_group` corporate-family rollup in
the crosswalk upgrade. Not ingested yet.
