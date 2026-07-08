
# Goal & Definition of Done *(added 2026-07-08)*

**What this is:** a regulatory-intelligence platform over SEC filings
(Form ADV/ERA, Form D, state advisers) that tracks private funds and the
service providers around them — who forms, who closes, who switches
providers, and which auditors/admins look suspect.

**Audience:** owner-operated research tool for now; the live Streamlit
dashboard is the product surface.

**v1 — definition of done:** all 7 dashboard use cases live on Streamlit
Cloud, on top of stable provider IDs, with scheduled ingestion green and
the provider registry backed up. Still open for v1: use case 6 page,
use case 7 (spike first), registry wiring for AUDITOR / PRIME_BROKER /
MARKETER, registry backup, GLEIF refresh cadence.

**v2 — after v1:** layer 5 cohort models, service-provider bundle
recommendation, ontology-driven chatbot. Neo4j only if a graph-only
question justifies it (see go/no-go decision in the backlog).

# Ontology
see DomainModel.yml

# raw data ingestion
dlt

# Semantic Layer
dbt model
layer 1: raw data ingested from sec
layer 2: normalization
map service provider name to canonical name and id.
combine service providers into one table
layer 3: history
based on each entity id, get history of events
layer 4: derived table from history
current status
layer 5: define cohort, policy and business need
like cohort by AUM size, age, type.

# Knowledge Base
add service provider table to neo4j.

# Use Case
### dashboard
showing predefind questions like
1, recent formed funds based on form d, and fund closure in form adv comparison
2, fund changing service provider alert
3, count of fund forming by time
4, money raised in first round by time
5, sec era fund using non pcaob auditors
6, missing era filings
7, missing auditing report and not filing amendment in time

### recommendation
service provider bundle recommendation
### chatbot
generate sql query based on ontology, get the number and use llm to generate complete answer.

---

# Status Check (2026-07-03)

Verified plan against code:

| Plan item | Status |
|---|---|
| Layer 1–2 (ingest + normalization) | ✅ Built (`staging/`, `int_service_provider_links`, `service_provider_dim`) |
| Layer 3 (history) | ✅ Built for ERA (`era_filing_history`, `int_era_annual_snapshot`) |
| Layer 4 (current status) | ✅ Built for ERA (`era_latest_filing`, `service_provider_changes`) |
| Layer 5 (cohorts / policy) | ❌ Not built |
| Neo4j knowledge base | ❌ Not started (blocked on stable provider IDs — see below) |
| Dashboard use cases 1–4 | ✅ Live (pages 1–5) |
| Use case 5 (non-PCAOB auditors) | ✅ Done 2026-07-08 (`adviser_auditor_status` + Auditor Watch page; no external registry needed) |
| Use case 6 (missing ERA filings) | ⚠️ `adviser_filing_compliance` mart exists but no dashboard page |
| Use case 7 (late audit reports) | ❌ Not built |
| Recommendation / chatbot | ❌ Not started |

Docs drift: README repo-layout table omits `ingestion/attorneys/`.

## Next Steps (agreed 2026-07-08)

1. ~~**Back up `provider_registry`**~~ ✅ done 2026-07-08 (see P1).
2. **GLEIF refresh cadence** — decide + document (see Problem 3).
3. Use case 6 dashboard page (`adviser_filing_compliance` mart already exists).
4. Registry wiring for AUDITOR / PRIME_BROKER / MARKETER (Problem 1, item 3).
5. Use case 7 feasibility spike, then mart + page.
6. Layer 5 cohort models (v2 starts here).

---

# Improvement Plan: Service Provider Identity

## Problem 1 — Generated IDs are unstable

Fund admins (and any provider without a PCAOB/SEC/LEI number) get a
content-derived ID: `NAME:<md5(normalized name)>` for fund admins,
`NAME:<farm_fingerprint(type|name|city|country)>` for the rest
(`int_service_provider_links.sql`). Consequences:

- The ID **changes whenever its inputs change**: a normalizer tweak, a new
  seed alias, or a city-spelling variation re-mints the ID. History,
  `service_provider_yoy`, and the future Neo4j graph all silently break keys.
- For non-fund-admin types, city/country are inside the fingerprint, so an
  **office move or inconsistent city spelling looks like a provider change**
  in `service_provider_changes` (false "swapped" alerts).
- One firm can hold different IDs across provider types (custodian LEI vs
  broker SEC# vs marketer NAME-hash) with no crosswalk between them.

**Fix — mint IDs once, never derive them from content:**

1. [x] **Provider registry built.** *(done 2026-07-08)* `provider_registry`
   (intermediate/era): append-only incremental model, one row per cluster
   key (the content-derived canonical_id at mint time) with a stable
   `sp_000123` surrogate. `full_refresh=false` in config — verified that
   `--full-refresh` cannot re-mint; re-runs append 0 rows with identical
   checksum; a deleted cluster re-mints at max+1. 5,206 providers minted.
   Bonus: keyed on match_key alone, so a firm filing under one SEC number as
   both marketer and custodian gets ONE provider_id (the missing crosswalk).
   If the table is ever lost, restore from a BigQuery snapshot — never re-run
   from scratch. Fund-admin canonical_id is wired through it:
   `int_service_provider_links_registered` swaps in the sp_ id (content key
   kept as legacy_canonical_id); all four service-provider marts consume the
   registered view; dashboard pages 2 & 8 verified. Other provider types
   pass through unchanged until item 3.
2. [x] **Match evidence separate from identity.** *(done 2026-07-08)*
   Registry rows carry mint-time evidence: PCAOB/SEC/CRD numbers, reported
   LEI, GLEIF LEI candidate + confidence from int_fund_admin_lei_map, and
   match_type (pcaob_number / sec_number / lei / seed_alias /
   name_fingerprint) + first_seen_filing_month.
3. Drop city/country from identity for all types (already done for fund
   admins); keep them as attributes, use them only as fuzzy-match evidence.
   When this lands, the NAME-fingerprint types can switch their canonical_id
   to provider_id in the registered view the same way fund admins did.
   *Progress 2026-07-08:* CUSTODIAN is now LEI-validated (reported LEIs are
   only trusted when they exist in GLEIF — ~30% of distinct reported values
   were EINs/CIKs/CRDs/typos; junk falls back to NAME fingerprint) and wired
   through the registry (sp_ ids in all marts). Remaining: AUDITOR /
   PRIME_BROKER / MARKETER, and dropping city/country from the custodian
   NAME fallback — careful with generic bank names ("FIRST NATIONAL BANK")
   that are genuinely different firms per country.

## Problem 2 — Fund admin alias seed is a flat, error-prone CSV

`seeds/fund_admin_aliases.csv` (~600 rows) conflates typo fixes, brand
rollups, and corporate-family judgments in two columns with no provenance.
Known errors found on review:

- [x] `CITI FUND SERVICES OHIO INC. → CITCO FUND SERVICES INC.` — Citi ≠ Citco; now maps to itself. *(fixed 2026-07-03)*
- [x] Canonical `STANDISH MAMAGEMENT LLC` typo → `STANDISH MANAGEMENT LLC` across all 8 Standish rows. *(fixed 2026-07-03)*
- [x] `THE APEX GROUP` now rolls up to `APEX FUND SERVICES LLC` like the other Apex variants. *(fixed 2026-07-03)*
- [x] `GRYPHON INVESTORS INC` unmerged from Gryphon Fund Group; maps to itself. *(fixed 2026-07-03)*
- [x] `SSC …` canonicals renamed to `SS&C TECHNOLOGIES`. *(fixed 2026-07-03)*

Full structural audit 2026-07-08 (dup rows, multi-mapping, chains, case/
whitespace, normalization-aware self-mapping + norm-key collisions): clean
except three fixes applied:

- [x] `NORTH MOUNTAIN FUND SERVICES` merged into `NORTHMOUNTAIN FUND SERVICES
  LLC` — all filing variants are the same Danville, CA firm. *(fixed 2026-07-08)*
- [x] `STEADFAST GROUP` / `THE STEADFAST GROUP` were two canonicals colliding
  on the same norm key (min() picked one silently); unified display to
  `THE STEADFAST GROUP` (no ID churn — light norm strips "the"). *(fixed 2026-07-08)*
- [x] Added `SS&C TECHNOLOGIES` self-mapping row (norm "ss c") so
  ampersand-spelled filings exact-match; today's filings all spell "SSC" so
  this is future-proofing. *(fixed 2026-07-08)*

Known caveat (not an error): 4 rows normalize to empty under the aggressive
normalizer (e.g. `CORPORATION SERVICE COMPANY`) and only match via the fuzzy
fallback. NB the seed is CRLF — sed/grep against it need `\r`-aware patterns.

> After seed changes: `dbt seed && dbt run -s int_service_provider_links+`.
> Note: these fixes change the affected `NAME:` canonical_ids — expected churn
> until the stable provider registry (below) lands.

**Fix — upgrade the seed to a crosswalk with provenance:**

1. Widen schema: `raw_name, canonical_name, parent_group, match_type,
   confidence, source, added_date`. `parent_group` separates office-level
   identity from corporate family (Apex offices vs Apex Group; Ultimus
   LeverPoint vs Leverpoint) so rollup level is a query-time choice instead
   of a hard-coded merge.
2. Add a **review queue**: fuzzy scores in the 0.80–0.92 band go to a
   `fund_admin_review.csv` for human triage instead of being silently
   dropped (today: auto-apply ≥ 0.92, ignore below).
3. Add dbt tests on the seed: canonical_name must also appear as a raw_name
   mapping to itself; no raw_name maps to two canonicals; (with registry)
   no two canonicals share a registry number.

## Problem 3 — Non-US fund admins missing

The seed was built from US-centric discovery; international admins fall
through to self-hash IDs with raw-name display.

1. [x] **GLEIF LEI is the answer for non-US identity** — *(data layer done
   2026-07-08)* `ingestion/gleif/` loads the golden copy Level 1 into BQ
   (`gleif.lei_records` 3.37M rows, `gleif.lei_names` 4.0M name variants;
   manual/on-demand, no schedule). dbt: `stg_gleif_lei_*` +
   `int_fund_admin_lei_map` — one row per fund-admin canonical_id with best
   LEI candidate, match_tier (1 exact / 2 aggressive+country) and
   match_confidence (high/medium/low; high = multi-token key + country
   corroborated). Coverage: 363/1,120 admin identities matched ≈ 71% of
   filing volume; Lux 74/181, Ireland 31/68, Cayman 18/50. Deliberately a
   MAPPING table — canonical_id rewiring waits for the provider registry
   (sequencing #2), which should consume match_confidence='high' rows.
   Parent relationships need the Level 2 (rr) file — not ingested yet.
   - [ ] **Refresh cadence (added 2026-07-08).** The golden copy was a
     one-time manual load; LEIs are issued and lapse continuously, so the
     match map drifts stale. Decide + document a cadence — quarterly, or at
     minimum before each registry-wiring milestone. Re-running is safe: the
     registry only consumes the map at mint time, so a refresh never churns
     existing `sp_` ids.
2. Run `scripts/discover_unknown_fund_admins.py` with a country breakdown
   (group unmatched raw_names by filing country) to prioritize which non-US
   admins to seed first.
3. Extend the jurisdiction wordlist in `normalize_fund_admin_name()` — it
   handles Cayman/Lux/Ireland/etc. but misses: `bvi, virgin, malta, cyprus,
   dublin, dubai, uae, netherlands, switzerland, zurich, india, canada,
   australia, japan, korea`.
4. Longer term: replace the bespoke cross-join fuzzy layer with a dedicated
   entity-resolution tool (e.g. Splink) run offline; dbt consumes the
   resulting crosswalk table. Scales better than SQL cross joins as the
   provider universe grows.

## Sequencing

1. ~~Fix the known seed errors~~ ✅ done 2026-07-03; full audit + 3 more fixes 2026-07-08.
2. ~~Provider registry with stable surrogate IDs~~ ✅ done 2026-07-08 (fund
   admins wired through; Neo4j no longer blocked on IDs).
3. GLEIF LEI enrichment — ✅ data + matching map done 2026-07-08 (see Problem 3);
   the `NAME:` → `LEI:` ID upgrade itself is deferred INTO the registry step
   so IDs only churn once.
4. Crosswalk schema upgrade + review queue.
5. Grain/uniqueness dbt tests on ERA models and the new registry (existing deferred TODO).

---

# Improvement Backlog (beyond provider identity)

Codebase-wide review, 2026-07-03. Grouped by priority.

## P1 — Correctness & data gaps

- [x] **Broker-dealer backfill wrote the wrong response body.**
  `ingestion/broker-dealer/download_bd_file.py:37` wrote `response.content`
  (the current month's 404 page) into the previous month's file instead of
  `response_previous.content`. *(fixed 2026-07-03; check `files/` for any
  corrupted previously-downloaded month.)*
- [x] ~~Daily Form D crawler rows never reach the marts~~ **False alarm** —
  the union already exists: all four `stg_form_d_*` models union
  `formd_crawler` with the quarterly bulk, deduped by accession number
  (quarterly wins). The claim came from a stale NOTE in
  `orchestration/flows.py`, now corrected. *(verified 2026-07-03)*
- [x] **ERA monthly ingestion silently stalled at April 2026.**
  `era_ingestion.update_monthly` ran EXTRACT on the STRING `date_submitted`
  column; BigQuery rejected the query and the broad except swallowed it, so
  the daily ERA flow no-op'd green while May/June 2026 went unloaded. Fixed
  with SAFE.PARSE_DATE + loud re-raise; May+June backfilled. *(fixed 2026-07-06)*
- [x] **Broker-dealer withdrawn_month overwritten every month.** Withdrawn
  master rows were re-stamped with the current month on every merge,
  destroying withdrawal history. Fixed transition logic (added
  `Reregistered` status: new start_month, keeps original withdrawn_month),
  rebuilt master from the raw table, caught up 03–06/2026. *(fixed 2026-07-06)*
- [x] **dbt source freshness checks.** *(done 2026-07-08)* All five sources
  now have `loaded_at_field` + warn/error thresholds matched to cadence in
  `models/staging/sources.yml` (dlt tables use `_dlt_load_id` — advances only
  when rows land, the exact stall signal; state feed uses `snapshot_date`;
  broker-dealer uses `LAST_DAY(file_month)`). A `dbt_source_freshness` task
  in `orchestration/flows.py` runs after ingest in every flow — including the
  short-circuit branches of era/quarterly/BD — and always AFTER ingest so a
  stale source never blocks its own self-heal. Verified: 20/20 pass live;
  negative test (tightened threshold) exits 1 → flow fails → GH Actions red.
  Broker-dealer required a new `broker_dealer` source (freshness-only, no
  models — declared with a comment) + `broker_dealer_raw_dataset` var.
  Finding along the way: BQ `state_adviser.state_adviser_master` is a legacy
  pandas-era table (last written 2026-05-14, referenced by no model, ingest
  docstring says masters live in dbt now) — excluded from freshness,
  candidate to drop.
- [x] **Dashboard pages crash raw when BigQuery fails.** *(fixed 2026-07-08)*
  Added `run_query(sql)` to `dashboard/bq.py` (try/except → `st.error` with
  the BQ message + `st.stop`); all 15 query call sites across the 8 pages now
  route through it. (Page 4's existing "guard" was only an empty-df check,
  not exception handling.) Verified via `streamlit.testing.v1.AppTest`: all
  8 pages render against live BQ; a forced bad query shows the error box and
  halts instead of dumping a traceback.
- [x] **Back up `provider_registry`.** *(done 2026-07-08)* The registry's
  recovery story was "restore from a BigQuery snapshot" but nothing created
  one, and BQ time travel only covers 7 days — an accidental drop outside
  that window re-mints every `sp_` id and silently breaks all history keys.
  Now: `backup_provider_registry` task in `orchestration/flows.py`, called
  from BOTH branches of the era-monthly flow (idempotent per month via
  `CREATE SNAPSHOT TABLE IF NOT EXISTS`), writing
  `registry_backups.provider_registry_snap_YYYYMM` in a separate dataset
  (survives accidents on the dbt intermediate dataset); each snapshot
  self-expires after 190 days, so ~6 are kept with zero cleanup code.
  Restore procedure documented in the model header. Verified live:
  task run twice through a Prefect flow (2nd call no-op), snapshot holds
  all 5,300 rows, and a restore rehearsal (clone → checksum diff vs live
  table) matched exactly.

## P2 — Operational reliability *(deferred until Prefect is deployed — 2026-07-03 decision)*

Daily/monthly schedules re-run next cycle, so a transiently failed run
self-heals; hardening these is not worth it while running locally.
Revisit when Prefect moves to a real deployment:

- [ ] deferred: Prefect flow-level failure alerting (email/Slack hook).
- [ ] deferred: HTTP retry/backoff against SEC endpoints (fixed sleeps +
  only 200/404 handled today; a 5xx kills the run until the next schedule).
- [x] User-Agent strings normalized to `HedgeFundNet katechen150621@gmail.com`
  across Form D ingestion *(2026-07-06)*. Hardcoding itself stays — owner is
  fine with it. (Broker-dealer files still use the old xchencws address.)
- [ ] deferred: max-iterations guard on the `while True` loop in
  `form_d_detail.py:185`.

## P3 — Scale & cost (BigQuery)

- [ ] **Partition + cluster the history marts.** BigQuery supports yearly
  time partitioning directly — in dbt:
  ```yaml
  {{ config(
      materialized='table',
      partition_by={'field': 'filing_date', 'data_type': 'date', 'granularity': 'year'},
      cluster_by=['entity_key']
  ) }}
  ```
  Notes: partition by the *date column* with `granularity: 'year'` rather
  than a derived fiscal-year int (int-range partitioning also works but a
  date column prunes automatically when the dashboard filters on dates).
  Candidates: `era_filing_history`, `form_d_fund_history`,
  `form_d_pooled_funds`. Clustering on `entity_key` / `file_num` is the
  bigger win for the ERA marts — those tables are small enough that
  partition pruning saves little, but clustered joins/filters are cheaper
  regardless. Skip partitioning tables under ~1 GB.
- [ ] **All marts are full-refresh tables** (`dbt_project.yml`). Fine today;
  as history grows convert the large ones to incremental (pairs naturally
  with the partitioning above — incremental insert_overwrite by partition).

## P4 — Quality, config & hygiene

- [x] **dbt test coverage — staging & intermediate layers.** *(done 2026-07-03)*
  Added `unique_combination` generic test macro (no dbt_utils dependency) and
  grain tests: `int_era_filings_by_year` + `int_era_annual_snapshot`
  (entity_key, reporting_year), `int_service_provider_links` (exact-duplicate
  guard against double-ingestion), `stg_form_d_submission` (accession_number).
  All 19 tests pass. Validating grains against live data surfaced two findings:
  - **Fixed**: two advisers had duplicate (entity_key, reporting_year) rows —
    two annual amendments claiming the same fiscal year. `int_era_filings_by_year`
    now keeps the latest annual (qualify at the final join).
  - **Learned**: custodian `reference_id` references the fund/schedule entry,
    not the provider — one reference_id legitimately carries multiple
    custodians. Documented in schema.yml; do not treat
    (filing_id, reference_id) as a provider key.
  Next increment (optional): grain tests for the remaining staging models and
  `int_form_d_*`.
- [ ] **Pin requirements**: `dashboard/requirements.txt` and the ingestion
  requirements files are unpinned — non-reproducible deploys (Streamlit
  Cloud can break on a transitive upgrade). Lock with `pip-compile` or
  `pip freeze`.
- [ ] **Hardcoded `sec_filings_marts` dataset name** in all 8 dashboard pages
  (18 call sites). Centralize in `dashboard/bq.py` via env var.
- [ ] **Docs drift**: README repo-layout omits `ingestion/attorneys/`;
  dead commented-out code in `ingestion/adv-form/util.py:46-52`.
  *(Fixed along the way: CLAUDE.md now names dbt; README page count updated
  8 → 9 with Auditor Watch row, 2026-07-08.)*

## Data coverage — expand historical data (planned)

- [ ] **Expand Form D historical backfill beyond 2024.** Current bulk data
  starts at 2024 Q1; SEC publishes quarterly Form D data sets back to 2008.
  Expansion is a `backfill.py` run with an earlier `start_year` — do NOT
  crawl old daily indexes (per-filing metadata lookup only covers a CIK's
  ~1,000 most recent filings). Before running, read
  `ingestion/form-d/README.md` § "Potential concerns when expanding
  historical data": older ZIPs may have different columns, and the
  first-raise / newly-emerging marts will (correctly) reclassify funds once
  earlier history exists, so expect existing quarter counts to shift.
- [ ] Decide target depth (e.g. 2019+ for a 5-year lookback vs full 2008+)
  and check BigQuery cost impact before loading (~55k filings/year).
- [ ] **Load RIA data (code ready, never run).** `ria_ingestion.py` mirrors
  the ERA pipeline but has never been used — no `ria_adv` data exists yet.
  Plan: refactor `era_ingestion.py` into one shared ADV-filing ingestion
  module with an ERA/RIA flag (the two files are ~90% identical today), then
  start loading RIA through it. Until that refactor, leave `ria_ingestion.py`
  as-is (known: it references an undefined `gcp_credentials`; the refactor
  resolves it — do not patch in place).

## Structural improvements (2026-07-06 sweep)

Architecture-level review after the code-error sweep. Ordered by value.

- [ ] *(deferred 2026-07-06 — owner decision: BD is small, pandas handles it
  fine, and BD may be abandoned later; revisit ONLY if broker-dealer data
  gets used in the dashboard)* **Derive the broker-dealer master in dbt, not pandas.**
  `broker_dealer_raw` already holds every monthly snapshot in BigQuery, so
  status / start_month / withdrawn_month / Reregistered are pure
  window-function logic over `file_month` — exactly the pattern the state
  adviser pipeline already uses ("raw snapshots in BQ, derived state in
  dbt"). Moving it kills the merge-script bug class entirely (this week's
  withdrawn_month bug lived there), makes rebuilds a `dbt run`, and gets
  grain tests for free. `merge_files.py` shrinks to just the raw loader.
  While there: load `BrokerDealerList.py`'s auditor-scrape output to BQ
  instead of a local CSV — it's the input use case 5 (non-PCAOB auditors)
  needs, and today it's disconnected from the warehouse.
- [~] **One scheduler as source of truth.** *(mostly done 2026-07-06)*
  Documented in the root README: GH Actions is authoritative today (chosen
  over deploying Prefect for infra/cost reasons); `serve.py` mirrors the
  crons as the future Prefect spec. The missing broker-dealer schedule is
  added (`broker-dealer-monthly.yml`, daily 5th–31st with in-flow guard —
  it had no automation and sat un-updated at Feb 2026 until the 2026-07-06
  manual catch-up). Remaining: when Prefect gets a real deployment, move
  the crons there and delete the GH Actions schedules in the same change.
- [ ] **Shared ingestion library (`ingestion/common/`).** The
  BIGQUERY_SERVICE_ACCOUNT_JSON boilerplate (env read → json.loads →
  client) is copy-pasted in ~10 files, the SEC User-Agent string in 7, and
  month/date helpers exist in three flavors across dirs. One small module
  (bq client factory, HEADERS constant, date helpers) means credential
  handling and UA change in one place. The planned ERA/RIA flag refactor is
  the natural first tenant of this package.
- [ ] **Unit tests + CI for the pure logic.** There are zero Python tests;
  both of this week's silent bugs (withdrawn_month overwrite, ERA
  EXTRACT-on-STRING) were in small pure functions. Targets:
  `merge_month()`, the date/month helpers, `parse_xml_schema` parsers
  (`raw_data.xml` already exists as a fixture — move it to
  `tests/fixtures/`), and cleanup cutoff logic. A pytest job on push (the
  workflows requirements.txt already defines the env) plus a `dbt compile`
  check is cheap insurance.
- [~] **Get data artifacts out of git.** *(partially done 2026-07-06)*
  Deleted `formD_2025_Q4.csv` / `formD_leads_2025_Q4.csv` (data lives in the
  BigQuery bulk dataset) and removed the dead old-CSV-flow helpers from
  `broker-dealer/utils.py`. Kept per owner decision: broker-dealer CSVs
  (small, in use) and attorneys CSVs (NOT in BigQuery — they're the only
  copy of the scraped data; load or park them when the law-firm provider
  type gets picked up). Keep `raw_data.xml` as a future test fixture.

## Product gaps already in the plan (repeated here so the backlog is one list)

- [ ] Surface `adviser_filing_compliance` as a dashboard page (use case 6).
- [x] ~~PCAOB registry enrichment →~~ non-PCAOB-auditor page (use case 5).
  *(done 2026-07-08)* No external PCAOB registry needed — Form ADV
  self-reports `pcaob_registered` / `pcaob_inspected` per auditor (already
  in `stg_era_auditors`). New mart `adviser_auditor_status` (one row per
  adviser: auditor PCAOB status, AUM bucket, template-filing signal) + page
  `9_Auditor_Watch.py`. Findings: 812 lead advisers (29 ≥ $150M), 88 firms
  registered-but-not-inspected, and a fraud cluster — 98 "advisers" all
  audited by INDICATOR GLOBAL, all reporting exactly $80M AUM, crypto-scam
  naming (TOKIOBIT, NYDAO, fake "RENAISSANCE TECHNOLOGIES…"), one signatory
  literally "JJIMMI1". The `same_auditor_same_aum_advisers` column
  generalizes that signal; the page quarantines clusters ≥ 5 peers.
- [ ] Late-audit-report detection (use case 7). **Feasibility spike first
  (added 2026-07-08):** "late" = the custody-rule 120-day audited-financials
  distribution deadline (180 for fund-of-funds). Confirm the ERA extract
  actually carries fiscal-year-end and audit-distribution/delivery fields
  (ADV Schedule D 7.B.23) before committing to a mart — if they're absent,
  the use case needs a different definition or data source.
- [ ] Layer 5 cohort models (AUM size / age / type).
- [ ] **Neo4j go/no-go decision (added 2026-07-08).** No longer blocked —
  stable `sp_` ids exist — but don't build it by default: the chatbot plan
  is SQL-over-BigQuery and bundle recommendation is expressible over
  `service_provider_clients`. Write down the question only a graph answers
  (e.g. multi-hop shared-provider paths between advisers); if there isn't
  one, drop Neo4j from the plan instead of keeping it as ambient scope.
- [ ] **Broker-dealer use-or-park decision (added 2026-07-08).** BD ingests
  monthly but feeds no mart or dashboard page. Trigger: when use cases 6–7
  ship, either connect BD to a concrete use case or pause
  `broker-dealer-monthly.yml` (data stays in BQ; resuming is cheap).
