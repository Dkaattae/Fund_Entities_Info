
# Goal & Definition of Done *(added 2026-07-08)*

**What this is:** a regulatory-intelligence platform over SEC filings
(Form ADV/ERA, Form D, state advisers) that tracks private funds and the
service providers around them — who forms, who closes, who switches
providers, and which auditors/admins look suspect.

**Audience:** owner-operated research tool for now; the live Streamlit
dashboard is the product surface.

**v1 — definition of done:** all 7 dashboard use cases live on Streamlit
Cloud, on top of stable provider IDs, with scheduled ingestion green and
the provider registry backed up.

**v1 closeout checklist (2026-07-10 evening):**

| DoD item | Status |
|---|---|
| Stable provider IDs (all 5 types through the registry) | ✅ complete — AUDITOR wired 2026-07-10 via PCAOB ingestion, the last type |
| Provider registry backed up | ✅ monthly snapshots since 2026-07-08 |
| All 7 use-case pages built | ✅ pages 1–11 in repo, AppTest-verified |
| Use cases live on Streamlit Cloud | ✅ owner verified 2026-07-10 — pages 10/11 showing on the live app |
| Scheduled ingestion green | ⏳ was RED 2026-07-09/10: unpinned workflow deps let pip backtrack dbt to 1.7 (can't parse the `arguments:` test-config key). Pin `dbt-bigquery>=1.11,<1.12` landed 2026-07-10 13:48 (commit 406f048), AFTER the day's failed runs. Verified locally same evening: a fresh venv resolve of `.github/workflows/requirements.txt` yields dbt-core 1.11.12 / protobuf 6.33.6 and `dbt source freshness` passes with it. Confirm tomorrow's scheduled runs (~08:00–12:00 UTC) are green — the token can't dispatch workflows manually. |

*(Done since written: registry backup; GLEIF refresh cadence + schedule;
use case 6 page; use case 7 mart + page; PRIME_BROKER and MARKETER wiring;
BD master migrated to dbt; AUDITOR wiring via the new PCAOB ingestion —
all 2026-07-10.)*

**v2 — after v1:** layer 5 cohort models, service-provider bundle
recommendation, ontology-driven chatbot. Neo4j only if a graph-only
question justifies it. **Detailed plan: see "# v2 Plan" section below
(drafted 2026-07-10).**

# v2 Plan (drafted 2026-07-10 — planning only, no v2 code yet)

**Theme:** v1 *tracks what happened* (formations, closures, switches,
compliance flags). v2 *answers questions and recommends*: segment the
market (cohorts), suggest provider bundles, and let the owner ask ad-hoc
questions in English. Everything stays SQL-over-BigQuery on the stable
`sp_` identity layer v1 finished; the dashboard remains the product surface.

**What v2 is deliberately NOT:** no Neo4j up front (deferred behind the
chatbot gate — decision below), no
ML models where counting answers the question, no multi-tenant/product
hardening — still an owner-operated research tool.

## Phase 0 — platform hardening (do first, ~small)

Cheap insurance before building on top; all are existing backlog items
promoted because v2 stacks more weight on the same pipelines:

1. **Lock `.github/workflows/requirements.txt`** (pip-compile or freeze).
   Unpinned deps broke all CI twice (fastapi 2026-06-16, dbt→1.7 downgrade
   2026-07-09/10). Do dashboard + ingestion requirements at the same time —
   Streamlit Cloud deploys are equally unpinned.
2. **pytest + dbt-compile CI on push** (backlog "Unit tests + CI"): the two
   silent July bugs (withdrawn_month overwrite, EXTRACT-on-STRING) were in
   small pure functions. Targets: `merge_month()`, date/month helpers,
   `parse_xml_schema` (fixture exists), plus `dbt compile` as a parse gate.
3. **Prefect go/no-go stays deferred** (P2): GH Actions remains the
   scheduler until something forces a real Prefect deployment. Revisit only
   if v2 adds a pipeline that needs event-driven runs or alerting.
4. Partition/cluster and incremental marts: only when a mart passes ~1 GB
   (P3 thresholds unchanged). Not expected during v2.

## Phase 1 — Layer 5 cohort models (no new data needed)

Cohorts turn "3,409 overdue funds" into "overdue funds are concentrated in
sub-$150M, non-US-domiciled, first-year advisers" — and they are the
segmentation the recommender conditions on.

**Cohort dimensions** (all derivable from existing models):

- `aum_bucket` — from `int_era_annual_snapshot.assets_under_management`
  (NOT the raw filing: amendments leave AUM blank = unchanged). Buckets at
  regulatory boundaries: <$25M / $25–150M / ≥$150M (the ERA exemption
  ceiling; Auditor Watch already flags ≥$150M) / ≥$1B.
- `adviser_age_bucket` — age since first regulatory appearance:
  min(first ERA filing, earliest linked Form D first_sale_date,
  incorporation date where reported). **Caveat:** ERA history starts at
  backfill_start_year=2025, so ERA-only age is left-censored; the Form D
  historical backfill (Phase 2) is what makes age honest beyond ~2 years.
- `strategy_mix` — from `stg_era_funds.fund_type` (Schedule D 7.B.1:
  hedge / private equity / venture / real estate / liquidity / securitized
  / other), rolled up per adviser (dominant type + is_multi_strategy flag,
  plus is_fund_of_funds).
- `domicile_mix` — US-only vs offshore (Cayman/Lux/Ireland/other) from
  fund country + adviser main_country.
- `fund_count_bucket` and `org_form` as secondary dims.

**Models** (new `marts/era` unless noted):

- `adviser_cohort_dim` — one row per entity_key (latest state) with all
  cohort columns; grain-tested.
- `adviser_cohort_history` — one row per (entity_key, reporting_year) so
  cohort migration (an adviser crossing $150M) is queryable; built on
  `int_era_annual_snapshot`.
- `provider_cohort_share` — provider × provider_type × cohort × year:
  client count, share within cohort, net wins/losses joined from
  `service_provider_changes`. This is the market-share cut the dashboard
  and the recommender both read.

**Surface:** extend page 8 (Service Provider Directory) with a cohort
filter, or a new "Market Share by Cohort" page. Acceptance: cohort columns
grain-tested; one page live; provider_cohort_share reconciles to
service_provider_clients totals.

## Phase 2 — data-depth enablers (parallel track, feeds Phases 1/3)

Ordered by value-per-effort; none block Phase 1 starting:

1. **Form D historical backfill to 2019** (5-year lookback). Enables honest
   adviser/fund age and gives the recommender formation-time provider
   choices to learn from. Read `ingestion/form-d/README.md` concerns first
   (older ZIP schemas differ; first-raise marts will correctly reclassify).
   ~55k filings/yr × 5 = ~275k filings; check BQ cost before loading. Full
   2008+ depth only if a v2 question actually needs it.
2. **RIA ingestion** via the planned shared ADV-module refactor
   (`era_ingestion.py` + `ria_ingestion.py` are ~90% identical). Unlocks:
   the full SEC adviser universe (cohorts stop being ERA-only), validation
   of marketer '801-' numbers (currently passed through unvalidated), and
   a bigger training base for the recommender. This is the largest enabler
   — schedule it mid-v2, not first.
3. **GLEIF Level 2 (rr) parent relationships** → `parent_group` on the
   provider registry/crosswalk (Problem 2 item 1). Needed by the
   recommender to stop treating Apex-office-A → Apex-office-B as a
   "switch" or a "recommendation". Pairs with the crosswalk schema upgrade
   + review queue already specced in Problem 2.
4. **FINRA broker-dealer firm list** (access details in backlog): CRD ↔
   file-number crosswalk on the BD master. Small, self-contained.
5. **Auditor Watch enrichment** (PCAOB follow-up): add
   `pcaob_number_verified` + inspection evidence from the already-loaded
   `pcaob.firm_inspections` to `adviser_auditor_status`, so page 9 stops
   relying purely on self-reported flags.

## Phase 3 — service-provider bundle recommendation (needs Phase 1 + 2.3)

**Definition:** an adviser's *bundle* = its current set of providers across
the 5 roles (from `int_service_provider_links_registered`, latest filing,
keyed by stable sp_ ids, rolled up to parent_group).

**Approach — counting before ML.** At this scale (~20k advisers, ~5k
providers) market-basket statistics answer the question:

- `provider_pair_affinity` mart: for provider pairs (A-as-admin,
  B-as-auditor…) within a cohort — support, confidence, lift vs cohort
  baseline. Computed in SQL; no new infra.
- `bundle_recommendation` view: given (cohort, partial bundle) → ranked
  co-occurring providers per missing role, excluding same-parent trivia,
  with "N advisers like this use X" as the explanation. Explainability is
  the product: every suggestion cites its counts.

**Evaluation before surfacing:** holdout = advisers first seen in the
latest year; score top-3 hit rate per role against (a) cohort-popularity
baseline and (b) global popularity. Ship only if it beats (a). Record the
numbers here.

**Surface:** new dashboard page ("Provider Bundles"): pick cohort + known
providers → ranked suggestions per empty role. Cold start (empty bundle) =
cohort market-share leaders from `provider_cohort_share`.

## Phase 4 — ontology-driven chatbot (needs Phase 1; independent of 2/3)

**Architecture (SQL-over-BigQuery, no graph):** Streamlit chat page →
LLM (Claude API) with a *semantic-layer prompt* = DomainModel.yml +
curated mart/column descriptions from schema.yml → model emits SQL →
guardrails execute it → model composes the answer from returned rows,
always showing the SQL it ran.

**Guardrails (non-negotiable, in this order):**
- Separate read-only service account with access to the marts dataset ONLY
  (not raw/intermediate/registry).
- SELECT-only statement validation + allowlisted tables.
- `dry_run` first: reject queries over a bytes-scanned cap; enforce LIMIT
  and a query timeout.
- No multi-turn write-back, no DDL, secrets via Streamlit secrets
  (`ANTHROPIC_API_KEY`).

**Build order:** (1) curate schema.yml descriptions — they become the
prompt, and gaps become wrong SQL; (2) eval set FIRST: the 7 predefined
use-case questions plus ~20 phrasings, scored for SQL correctness against
known answers; (3) only then the chat page. Model choice + cost cap
decided at build time (small/mid tier likely sufficient for SQL
generation; measure on the eval set).

**Success bar:** ≥90% correct on the eval set; every answer cites its SQL;
a failed/blocked query degrades to "here's the SQL I would run" instead of
hallucinated numbers.

## Neo4j — DEFERRED, with the chatbot as its decision gate (owner call 2026-07-10)

Not dropped — deferred. The SQL chatbot (Phase 4) goes first because the
candidate graph questions (multi-hop shared-provider paths between
advisers; fraud rings à la INDICATOR GLOBAL — shared auditor + identical
AUM + shared signatory) are 1–2 joins at current scale, and the fraud
cluster was in fact found with SQL in v1. **The trigger to adopt Neo4j is
the chatbot eval:** if the SQL agent proves not good enough — repeatedly
failing or producing unreadable SQL on graph-shaped questions (≥3-hop
traversals, path/ring discovery) — build the Neo4j knowledge base then,
loading `service_provider_clients` + the registry (stable sp_ ids make
this safe now). Until that trigger fires, no graph work.

## Sequencing

1. Phase 0 (hardening) — immediately, small.
2. Phase 1 (cohorts) — first feature; no new data needed.
3. Phase 2 starts in parallel after Phase 1's models exist: 2.1 Form D
   backfill and 2.5 Auditor Watch enrichment first (cheap), then 2.3 GLEIF
   L2 + crosswalk (recommender prerequisite), 2.2 RIA (largest), 2.4 FINRA.
4. Phase 3 (recommender) — after Phase 1 + 2.3.
5. Phase 4 (chatbot) — anytime after Phase 1; can be pulled earlier since
   it depends only on schema docs + eval set, not on Phases 2–3.

**v2 definition of done:** cohort models + one cohort page live;
recommender beats the cohort-popularity baseline and has a page; chatbot
answers the 7 canonical questions at ≥90% on the eval set from the live
dashboard; Neo4j decision resolved via the chatbot gate (stay deferred,
or build it if the SQL agent falls short on graph-shaped questions);
Phase-0 locks and CI in place. Decision gates recorded here as they're
hit (Form D depth, RIA timing, Neo4j trigger).

---

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
| Use case 6 (missing ERA filings) | ✅ Done 2026-07-10 (own page `10_Missing_ERA_Filings.py`; was buried in a page-2 tab) |
| Use case 7 (late audit reports) | ✅ Done 2026-07-10 (`fund_audit_compliance` + Late Audit Reports page; spike found the fields exist) |
| Recommendation / chatbot | ❌ Not started |

Docs drift: README repo-layout table omits `ingestion/attorneys/`.

## Next Steps (agreed 2026-07-08)

1. ~~**Back up `provider_registry`**~~ ✅ done 2026-07-08 (see P1).
2. ~~**GLEIF refresh cadence**~~ ✅ done 2026-07-10 — monthly, as a scheduled
   flow like every other source (see Problem 3).
3. ~~Use case 6 dashboard page~~ ✅ done 2026-07-10 — pulled the "Compliance
   Concerns" tab out of page 2 into its own page `10_Missing_ERA_Filings.py`
   (it was undiscoverable nested in a tab).
4. Registry wiring for AUDITOR / PRIME_BROKER / MARKETER (Problem 1, item 3).
   **AUDITOR needs a PCAOB data source first** (owner decision 2026-07-10):
   ingest the PCAOB registered-firms registry and validate reported PCAOB
   numbers against it before trusting them as identity — same pattern as
   custodian LEI validation (~30% of reported LEIs were junk; expect the
   same class of typos/wrong-numbers here). Not scheduled for a specific
   date; PRIME_BROKER / MARKETER can proceed independently of it.
   **PRIME_BROKER: ✅ wired 2026-07-10** (validate the reported SEC
   file number against our own BD master; no new data source needed).
   `stg_era_primary_brokers.sec_number` ('8-34354') joins
   `broker_dealer.broker_dealer_master.film_number`, which IS the SEC
   broker-dealer file number zero-padded ('8-1447' → '00801447': prefix
   LPAD to 3 + serial LPAD to 5 — naive digit-stripping breaks on short
   serials). Measured 2026-07-10: 407 distinct PB tuples → 131 report a
   sec_number, 108 validate against the master (~82%; rest = withdrawn
   firms/typos → NAME fallback). CRD adds nothing: zero tuples report a
   CRD without also reporting a sec_number (the BD table has no CRD
   anywhere — the `crd` column is empty; FINRA enrichment below would add
   it later). 276 name-only tuples fall back to NAME fingerprint like the
   other types. This makes the BD master a consumed identity registry —
   resolving the "broker-dealer use-or-park decision" (backlog) toward USE.
   *Implemented same day:* BD-master validation join in
   `int_service_provider_links` (reported '8-xxxxx' strings kept as-is —
   formats verified uniform, so the 108 validated keys' canonical_ids were
   unchanged and no existing sp_ ids churned); PRIME_BROKER added to the
   sp_-swap list in `int_service_provider_links_registered`. Registry
   appended exactly 33 rows (junk-SEC fallback clusters). Verified: all
   6,232 PB mentions carry sp_ ids (108 providers via validated SEC number,
   279 via NAME fallback), 19/19 tests pass, pages 2 & 8 render, and the
   crosswalk works — Goldman/Merrill/UBS each hold ONE sp_ id across their
   PRIME_BROKER/CUSTODIAN/MARKETER roles.
   **MARKETER: ✅ wired 2026-07-10, same pattern.** Marketers report either
   a broker-dealer number ('8-…', 330 tuples: 298 provider ids validate vs
   the BD master) or an adviser number ('801-…', 69 tuples: pass through
   UNVALIDATED — no RIA registry loaded yet; validate them when the planned
   RIA ingestion lands). 775 name-only clusters fall back to NAME
   fingerprint. Found + fixed along the way: the file-number normalization
   LPAD-TRUNCATES over-long serials, so typo'd numbers ('8-692444', 6-digit
   serial) falsely validated as other real firms ('8-69244') — now guarded
   by a bounded format regex in the shared `bd_file_key` macro; one
   previously false PB validation was demoted (108 → 107 validated).
   Verified: all 113,126 marketer mentions carry sp_ ids (1,142 providers),
   19/19 tests, pages 2 & 8 render, registry appended 41 rows.
   Remaining wiring: AUDITOR only (blocked on PCAOB source).
5. ~~Use case 7 feasibility spike, then mart + page~~ ✅ done 2026-07-10 —
   spike confirmed feasibility (see the backlog item for details), then
   `stg_era_funds` + `fund_audit_compliance` mart + page
   `11_Late_Audit_Reports.py`.
6. ~~PCAOB registered-firms ingestion → AUDITOR wiring~~ ✅ done 2026-07-10
   (see the "PCAOB Ingestion Plan" section below for outcome + numbers).
   Provider-identity wiring is now complete for all 5 types.
7. Layer 5 cohort models (v2 starts here).

---

# PCAOB Ingestion Plan (AUDITOR wiring — planned 2026-07-10)

**✅ BUILT 2026-07-10 (same day).** Outcome summary; original plan kept below
for the decision trail:

- **Decision gate result:** Form AP bulk CSV alone validated only 52.1% of
  the 445 distinct reported pcaob_numbers (84.7% mention-weighted) — the
  misses were real private-fund auditors that never audit issuers (PwC
  Channel Islands, KPMG Luxembourg, RSM Cayman…). So the endpoint discovery
  in option (3) was done: the registered-firms directory page is a JS app
  over a **Hawksearch JSON search API** (client GUID + endpoint read from
  the page's `data-*` attributes, pinned in `ingestion/pcaob/
  pcaob_ingestion.py`). `Content Type = Firm` returns the COMPLETE directory
  — 4,084 firms incl. withdrawn/revoked — in ~43 paged requests, a strict
  superset of both the Form AP firm list and the inspections list.
- **Coverage (measured 2026-07-10):** 399/445 distinct reported numbers
  validate (89.7%); mention-weighted 36,915/37,260 = **99.1%**. Junk rate
  10.3% (typos, made-up numbers like 111111/12345, member firms under wrong
  ids) — consistent with reported LEIs (~30%) and BD numbers (~18%).
  Withdrawn/revoked firms count as valid identity (same reasoning as
  withdrawn BDs in the BD master); registration_status is an attribute.
- **Built:** `ingestion/pcaob/` (dlt → `pcaob.registered_firms` +
  `pcaob.firm_inspections`, load_ts stamped, raw snapshots in gitignored
  files/); dbt `pcaob` source w/ freshness + `stg_pcaob_registered_firms`
  (unique/not_null firm_id); auditors CTE in `int_service_provider_links`
  nulls unvalidated pcaob_numbers (they fall to NAME fingerprint); AUDITOR
  added to the sp_ swap — the registered view now swaps ALL five types;
  `provider_registry` tagged pcaob+gleif so both flows mint; `pcaob_monthly`
  flow + `pcaob-monthly.yml` (cron 2nd–8th 04:00 UTC, before gleif/era) +
  serve.py mirror.
- **Verified:** pcaob_number is numeric in source (no LPAD-truncation class
  of issue); zero churn — all 399 validated `PCAOB:` keys survived
  byte-identical, 0 new PCAOB keys, 46 junk clusters demoted to NAME;
  registry appended exactly 8 rows (junk-fallback clusters), no duplicate
  match_keys; all 41,983 auditor mentions carry sp_ ids (758 providers: 399
  via validated PCAOB number, 359 via NAME fallback); 25/25 dbt tests pass;
  AppTest pages 2, 8, 9 render; flow runs end-to-end cold-start and the
  guard no-ops on rerun.
- **Optional follow-up (not built):** registry-verified columns on
  `adviser_auditor_status` (`pcaob_number_verified`, inspection evidence
  from `pcaob.firm_inspections`) so Auditor Watch stops relying purely on
  self-reported flags.
- **Ops note:** if the directory fetch starts failing, re-inspect the
  registered-firms page for a rotated Hawksearch client GUID (documented in
  the ingest script + README). The fetch refuses to replace the table if
  fewer than 3,500 rows come back.

**Goal:** validate reported auditor PCAOB numbers in `stg_era_auditors`
against the actual PCAOB registry — the custodian-LEI / prime-broker-BD
pattern — then add AUDITOR to the registered view's sp_ swap. Completes
provider-identity wiring for all 5 types (the last open v1 item).

## Source options (decide by measuring coverage, cheapest-official first)

1. **AuditorSearch / Form AP dataset (preferred start).** Official bulk CSV
   download, updated daily (pcaobus.org/resources/auditorsearch). Carries
   Firm ID (= the PCAOB number advisers report) + firm name + country.
   Caveat: it only covers firms that filed Form AP (public-company/issuer
   audits) — private-fund-only auditors never appear, so it is likely a
   SUBSET of the registry. Zero scraping risk, so start here and measure.
2. **Firm inspection reports datasets.** Official CSV/XML/JSON downloads
   (pcaobus.org/oversight/inspections/firm-inspection-reports). Inspected
   firms only — not the registry, but gives per-firm inspection evidence
   that can cross-check the self-reported `pcaob_inspected` flag on
   filings (Auditor Watch enrichment).
3. **Registered-firms directory** (pcaobus.org/oversight/registration/
   registered-firms) — the COMPLETE list, rendered by a JS app; the
   underlying JSON endpoint is not yet identified (repo notes reference
   `pcaobus.org/api/firm/{id}/filings`, so an `/api/firm` surface exists).
   Discovery step: inspect the page's network calls for the list endpoint
   or an export. Check ToS before automating.
4. **RASR** (rasr.pcaobus.org) — ASP.NET per-firm public summary pages
   keyed by an opaque FirmID hash; enumerating via its search page is
   classic scraping. Last resort only.

**Decision gate:** load (1), then measure — what % of distinct reported
`pcaob_number`s in our ERA auditors match? (Expect junk like the other
registries: ~30% of reported LEIs, ~18-20% of reported BD numbers were
invalid.) If real auditors are missing because they don't audit issuers,
do the endpoint discovery in (3) for the full directory; otherwise (1)+(2)
suffice and we skip scraping entirely.

## Ingestion (`ingestion/pcaob/`)

- `pcaob_ingestion.py`, dlt → BigQuery dataset `pcaob`
  (same stack as gleif/): download the official CSV(s), load
  `registered_firms` (firm_id, firm_name, country, …) and optionally
  `firm_inspections`, `write_disposition=replace`.
- Stamp a `load_ts` column at load time (GLEIF lesson: dlt's pandas/arrow
  path adds no `_dlt_load_id`; guard + freshness key off `load_ts`).
- House conventions: UA `HedgeFundNet katechen150621@gmail.com`, downloads
  land in a gitignored `files/`, README with tables/grain/cadence.

## Transform (dbt)

- `sources.yml`: new `pcaob` source (`pcaob_raw_dataset` var) with
  freshness on `load_ts` (warn 40d / error 55d, monthly cadence).
- `stg_pcaob_registered_firms` (staging/pcaob, tag `pcaob`; grain tests:
  unique firm_id, not_null).
- `int_service_provider_links` auditors CTE: trust a reported
  `pcaob_number` only when it exists in the registry; invalid ones fall
  back to the NAME fingerprint. BEFORE building: check reported-number
  format consistency (the LPAD-truncation lesson — bound the accepted
  format) and confirm validated `PCAOB:` canonical keys stay identical so
  no existing sp_ ids churn.
- `int_service_provider_links_registered`: add AUDITOR to the sp_ swap.
- Optional follow-up: `adviser_auditor_status` gains registry-verified
  columns (e.g. `pcaob_number_verified`, inspection status from source 2)
  so Auditor Watch stops relying purely on self-reported flags.

## Orchestration

- `pcaob_monthly` flow in `orchestration/flows.py` (route `pcaob`),
  mirroring gleif-monthly: `is_pcaob_loaded_this_month` guard on
  max(load_ts) → ingest → `dbt source freshness --select source:pcaob` →
  `dbt run/test --select tag:pcaob`.
- Cron daily-in-window **2nd–8th at 04:00 UTC** — before gleif-monthly
  (05:00) and era-monthly (06:00, window opens the 5th), so the registry
  mints new AUDITOR rows against a fresh PCAOB list the same way it does
  against a fresh LEI map.
- `.github/workflows/pcaob-monthly.yml` + mirror deployment in `serve.py`.

## Verification checklist (before calling it done)

- Coverage + junk-rate numbers recorded here (distinct reported
  pcaob_numbers validated / total).
- Zero churn of already-validated `PCAOB:` sp_ ids; registry delta =
  junk-fallback clusters only (append-only).
- 19/19 links tests still pass; AppTest pages 2, 8, 9 (Auditor Watch
  consumes auditor identity).
- Flow runs end-to-end locally (`python orchestration/flows.py pcaob`),
  guard no-ops on rerun.

---

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
   *Note 2026-07-10:* AUDITOR wiring is blocked on ingesting a PCAOB
   registered-firms data source — reported PCAOB numbers must be validated
   against the actual registry before being trusted as identity, exactly
   like custodian LEIs were validated against GLEIF (where ~30% of reported
   values turned out to be junk). See Next Steps item 4.
   *Done 2026-07-10 (later same day):* AUDITOR wired — PCAOB numbers
   validated against the ingested registered-firms directory (89.7% of
   distinct reported values valid, 99.1% mention-weighted); all five
   provider types now flow through the registry sp_ swap. Remaining from
   this item: dropping city/country from the NAME-fallback fingerprints
   (still per-type content keys today).

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
   - [x] **Refresh cadence (added 2026-07-08).** *(done 2026-07-10)* Monthly,
     scheduled like every other source: `gleif_monthly` flow in
     `orchestration/flows.py` + `gleif-monthly.yml` GH Actions workflow
     (cron daily 2nd–8th 05:00 UTC, in-flow guard no-ops once the month is
     loaded — deliberately before era-monthly's window opens on the 5th so
     the registry mints against a fresh LEI map). The ingest script now
     stamps a `load_ts` column (dlt's pandas/arrow path adds no
     _dlt_load_id); guard + source freshness (warn 40d / error 55d in
     sources.yml) key off it. Flow reruns `tag:gleif` (both stg models,
     `int_fund_admin_lei_map`, `provider_registry`) after each load.
     Re-running is safe: the registry only consumes the map at mint time,
     so a refresh never churns existing `sp_` ids.
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
  `pip freeze`. *This has now bitten twice in CI:* fastapi 0.137 broke
  prefect (pinned 2026-06-16), and on 2026-07-09/10 every scheduled run
  went red because pip backtracked dbt to 1.7 over a protobuf-7-era grpcio
  conflict (dbt 1.7 can't parse the `arguments:` key in generic test
  configs) — reactive pin `dbt-bigquery>=1.11,<1.12` added 2026-07-10.
  A full lock of `.github/workflows/requirements.txt` is the durable fix.
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

- [x] **Derive the broker-dealer master in dbt, not pandas.** *(done
  2026-07-10 — the 2026-07-06 deferral's trigger fired: BD master now feeds
  the identity layer via PRIME_BROKER validation, so the owner reversed the
  decision.)* `stg_broker_dealer_snapshots` + `int_broker_dealer_master`
  (tag `broker_dealer`) replay the raw monthly snapshots with window
  functions — same status semantics incl. Reregistered and the pandas
  quirks (initial-load rows have NULL start_month, was ''). Verified
  column-identical against the pandas-built table across all 3,609 CIKs
  before switchover. `merge_files.py` and `backfill.py` shrank to raw-only
  loaders; the flow runs raw load → freshness → dbt run/test tag:broker_dealer;
  `int_service_provider_links` now refs the dbt model. Legacy
  `broker_dealer.broker_dealer_master` is no longer written or consumed
  (freshness: null; candidate to drop, like state_adviser_master).
  Still open from this item: load `BrokerDealerList.py`'s auditor-scrape
  output to BQ instead of a local CSV — relevant again when the PCAOB
  source lands for AUDITOR wiring.
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

- [x] ~~Surface `adviser_filing_compliance` as a dashboard page (use case 6).~~
  *(done 2026-07-10)* Pulled the "Compliance Concerns" tab out of page 2 —
  where it had proven undiscoverable — into its own page
  `10_Missing_ERA_Filings.py` (KPIs, FYE/state/min-days filters, row detail,
  overdue-by-FYE rollup). Page 2 keeps New Advisers + provider-type tabs.
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
- [x] ~~Late-audit-report detection (use case 7).~~ *(done 2026-07-10)*
  Spike outcome: the ERA extract DOES carry the needed fields —
  `era_adv.funds` (Schedule D 7.B.1 Q23) has `annual_audit`,
  `fs_distributed`, and `unqualified_opinion` whose value
  **'Report Not Yet Received'** is an explicit audit-outstanding flag; the
  follow-ups are gated on annual_audit='Y' so audited rows always carry
  real answers (no amendment-sparsity problem). No audit-delivery DATE
  exists, so "late" = state-based: latest filing still shows the report
  outstanding/undistributed past adviser FYE + 120 days (180 for FoF; a
  benchmark — ERAs aren't literally subject to the custody rule's audit
  provision, and advisers must promptly amend 7.B.23.h when statements go
  out). Built: `stg_era_funds` (new source table declared),
  `fund_audit_compliance` mart (one row per audited fund on the latest
  filing; terminated advisers excluded; qualified opinions a separate
  status), page `11_Late_Audit_Reports.py` with an auditors-ranked-by-
  overdue-reports table. Live numbers: 3,409 overdue funds / 1,379
  advisers / $508B fund GAV; 498 funds carry qualified opinions.
- [ ] Layer 5 cohort models (AUM size / age / type).
- [x] **Neo4j go/no-go decision (added 2026-07-08).** ~~Write down the
  question only a graph answers; if there isn't one, drop it.~~
  *Resolved 2026-07-10: DEFERRED behind the chatbot gate (owner call —
  deferred, not dropped).* The SQL chatbot ships first; if its eval shows
  the SQL agent isn't good enough on graph-shaped questions (≥3-hop
  shared-provider paths, ring discovery), build Neo4j then. See the
  "Neo4j — DEFERRED" subsection of the v2 Plan.
- [x] **Broker-dealer use-or-park decision (added 2026-07-08).** ~~BD ingests
  monthly but feeds no mart or dashboard page. Trigger: when use cases 6–7
  ship, either connect BD to a concrete use case or pause
  `broker-dealer-monthly.yml` (data stays in BQ; resuming is cheap).~~
  *Resolved 2026-07-10: USE.* The PRIME_BROKER registry wiring (Next Steps
  item 4) validates reported SEC file numbers against
  `broker_dealer_master.film_number`, so the monthly BD ingest stays.
- [ ] **BD data enrichment via the FINRA Query API (added 2026-07-10,
  future).** The BD table has no CRD number anywhere; FINRA's
  "Broker-Dealer Firm List" dataset is the official machine-readable
  registry (all FINRA-registered BDs, queryable by CRD or in full) — the
  sanctioned alternative to scraping BrokerCheck (prohibited) or the PCAOB
  self-reported client CRDs (unreliable). Would add a CRD ↔ name/file-number
  crosswalk to `broker_dealer_master`. Access details:
  - Signup: create an **individual account** at https://developer.finra.org
    → API Console → provision a **Public** API credential (free tier;
    the paid "Firm credential" is only for member firms' own private
    registration records — not needed here).
  - Auth: OAuth2 client-credentials against the FINRA Identity Platform
    using the credential, then Bearer token on every call.
  - Base URL: `https://api.finra.org`; dataset group `registration`,
    name `brokerDealerFirmList` —
    data: `https://api.finra.org/data/group/registration/name/brokerDealerFirmList`,
    field list: `https://api.finra.org/metadata/group/registration/name/brokerDealerFirmList`.
  - Limits: 100 records/request default, 500 max (paginate with
    limit/offset); 1,200 sync requests/min per IP — a full pull of ~3.4k
    firms is a few dozen requests. Ingest as a small dlt REST source.
  - Docs: https://developer.finra.org/docs#query_api-registration-broker_dealer_firm_list_
