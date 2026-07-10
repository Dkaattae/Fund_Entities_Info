{{ config(
    materialized='incremental',
    full_refresh=false,
    on_schema_change='fail',
    tags=['gleif', 'pcaob']
) }}

-- Persistent service-provider registry (project_plan "Problem 1").
-- APPEND-ONLY: the first time a cluster key (today's content-derived
-- canonical_id) appears, it is assigned a surrogate provider_id
-- (sp_000123) that is NEVER changed or deleted. Matching logic can evolve
-- and re-mint cluster keys; assigned provider_ids do not move.
--   * full_refresh=false — `dbt run --full-refresh` will NOT rebuild this
--     table. Re-minting IDs breaks every downstream history. If the table
--     is ever lost, restore it from a BigQuery snapshot, do not re-run.
--     Monthly snapshots land in `registry_backups.provider_registry_snap_YYYYMM`
--     (era-monthly flow → orchestration/flows.py::backup_provider_registry;
--     each self-expires after 190 days). Restore from the NEWEST one:
--       CREATE TABLE `sec_filings_intermediate.provider_registry`
--       CLONE `registry_backups.provider_registry_snap_YYYYMM`;
--   * Rows carry mint-time EVIDENCE (registry numbers, GLEIF LEI candidate,
--     match_type) — auditable and reversible, separate from identity.
--   * One row per match_key, so a firm reported under the same SEC number
--     as both marketer and custodian gets ONE provider_id (the crosswalk
--     the old per-type IDs never had).

with links as (
    select *
    from {{ ref('int_service_provider_links') }}
    where canonical_id is not null
),

name_counts as (
    select canonical_id as match_key, raw_name, count(*) as n
    from links
    where raw_name is not null
    group by 1, 2
),

-- Deterministic display name: most-reported raw_name, ties alphabetical
-- (same rule as service_provider_dim).
display_names as (
    select
        match_key,
        array_agg(raw_name order by n desc, raw_name limit 1)[offset(0)] as display_name
    from name_counts
    group by match_key
),

clusters as (
    select
        l.canonical_id as match_key,
        string_agg(distinct l.provider_type, ',' order by l.provider_type) as provider_types,
        logical_or(l.alias_canonical_name is not null) as has_seed_alias,
        max(l.pcaob_number)     as pcaob_number,
        max(l.sec_number)       as sec_number,
        max(l.crd_number)       as crd_number,
        max(l.lei)              as reported_lei,
        min(l.filing_month)     as first_seen_filing_month,
        count(distinct l.filing_id) as filings_at_mint
    from links l
    group by 1
),

-- GLEIF candidate evidence for fund admins (mapping only — see
-- int_fund_admin_lei_map; 'high' is the programmatically trustworthy tier).
lei_evidence as (
    select
        canonical_id as match_key,
        lei              as gleif_lei,
        match_confidence as gleif_match_confidence
    from {{ ref('int_fund_admin_lei_map') }}
    where lei is not null
),

new_clusters as (
    select
        c.*,
        d.display_name,
        e.gleif_lei,
        e.gleif_match_confidence
    from clusters c
    join display_names d using (match_key)
    left join lei_evidence e using (match_key)
    {% if is_incremental() %}
    where not exists (
        select 1 from {{ this }} r where r.match_key = c.match_key
    )
    {% endif %}
)

select
    concat('sp_', format('%06d',
        {% if is_incremental() %}
        (select coalesce(max(cast(substr(provider_id, 4) as int64)), 0)
         from {{ this }})
        {% else %}
        0
        {% endif %}
        + row_number() over (order by match_key)
    )) as provider_id,
    match_key,
    case
        when match_key like 'PCAOB:%' then 'pcaob_number'
        when match_key like 'SEC:%'   then 'sec_number'
        when match_key like 'LEI:%'   then 'lei'
        when has_seed_alias           then 'seed_alias'
        else 'name_fingerprint'
    end as match_type,
    display_name,
    provider_types,
    pcaob_number,
    sec_number,
    crd_number,
    reported_lei,
    gleif_lei,
    gleif_match_confidence,
    first_seen_filing_month,
    filings_at_mint,
    current_timestamp() as minted_at
from new_clusters
