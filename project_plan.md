
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
| Use case 5 (non-PCAOB auditors) | ❌ No mart / page; needs PCAOB registry enrichment |
| Use case 6 (missing ERA filings) | ⚠️ `adviser_filing_compliance` mart exists but no dashboard page |
| Use case 7 (late audit reports) | ❌ Not built |
| Recommendation / chatbot | ❌ Not started |

Docs drift: README repo-layout table omits `ingestion/attorneys/`.

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

1. Add a persisted **provider registry** table (incremental dbt model or
   snapshot): first time a new cluster (normalized name + evidence) appears,
   assign a surrogate key (`sp_000123`) and keep it forever. Matching logic
   can evolve; assigned IDs do not. `canonical_id` in the links model becomes
   a lookup against this registry, not an expression.
2. Keep **match evidence separate from identity**: registry rows carry
   registry numbers (PCAOB/SEC/LEI/CRD), match_type (registry / seed-alias /
   fuzzy / manual), and confidence — auditable and reversible.
3. Drop city/country from identity for all types (already done for fund
   admins); keep them as attributes, use them only as fuzzy-match evidence.

## Problem 2 — Fund admin alias seed is a flat, error-prone CSV

`seeds/fund_admin_aliases.csv` (~600 rows) conflates typo fixes, brand
rollups, and corporate-family judgments in two columns with no provenance.
Known errors found on review:

- [x] `CITI FUND SERVICES OHIO INC. → CITCO FUND SERVICES INC.` — Citi ≠ Citco; now maps to itself. *(fixed 2026-07-03)*
- [x] Canonical `STANDISH MAMAGEMENT LLC` typo → `STANDISH MANAGEMENT LLC` across all 8 Standish rows. *(fixed 2026-07-03)*
- [x] `THE APEX GROUP` now rolls up to `APEX FUND SERVICES LLC` like the other Apex variants. *(fixed 2026-07-03)*
- [x] `GRYPHON INVESTORS INC` unmerged from Gryphon Fund Group; maps to itself. *(fixed 2026-07-03)*
- [x] `SSC …` canonicals renamed to `SS&C TECHNOLOGIES`. *(fixed 2026-07-03)*

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

1. **GLEIF LEI is the answer for non-US identity** — free bulk golden copy /
   API, global coverage, includes parent relationships (corporate family for
   free). Match name+country against GLEIF; a hit upgrades the NAME-hash to
   `LEI:` and covers most sizeable offshore admins (Cayman, Lux, Ireland,
   Channel Islands…).
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

1. ~~Fix the known seed errors~~ ✅ done 2026-07-03.
2. Provider registry with stable surrogate IDs (unblocks Neo4j + safe history).
3. GLEIF LEI enrichment (fixes non-US coverage and shrinks the NAME-hash population).
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
- [ ] **No dbt source freshness checks** (`models/staging/sources.yml`). If
  SEC stops publishing or an ingestion silently stalls, nothing alerts. Add
  `freshness: warn_after/error_after` per source matched to its cadence
  (ERA monthly, state feed daily, Form D crawler daily).
- [ ] **Dashboard pages crash raw when BigQuery fails.** Only
  `4_First_Round_Fundraise.py` guards its query. Wrap the shared query path
  in `bq.py` with try/except + `st.error(...)` so all 8 pages degrade
  gracefully.

## P2 — Operational reliability *(deferred until Prefect is deployed — 2026-07-03 decision)*

Daily/monthly schedules re-run next cycle, so a transiently failed run
self-heals; hardening these is not worth it while running locally.
Revisit when Prefect moves to a real deployment:

- [ ] deferred: Prefect flow-level failure alerting (email/Slack hook).
- [ ] deferred: HTTP retry/backoff against SEC endpoints (fixed sleeps +
  only 200/404 handled today; a 5xx kills the run until the next schedule).
- [ ] wontfix: User-Agent email hardcoded — owner is fine with it.
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
  `CLAUDE.md` still says "Transform tool: not yet selected" (it's dbt);
  dead commented-out code in `ingestion/adv-form/util.py:46-52`.

## Product gaps already in the plan (repeated here so the backlog is one list)

- [ ] Surface `adviser_filing_compliance` as a dashboard page (use case 6).
- [ ] PCAOB registry enrichment → non-PCAOB-auditor page (use case 5).
- [ ] Late-audit-report detection (use case 7).
- [ ] Layer 5 cohort models (AUM size / age / type).
