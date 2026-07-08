{{ config(materialized='table') }}

-- One row per (canonical_id, provider_type).
-- display_name, city, state, country all use the most-frequently-reported
-- value (mode via approx_top_count) so that a single mis-typed filing
-- (e.g. a full street address in the city field) cannot override the
-- correct value that the majority of advisers reported.

with links as (
    select * from {{ ref('int_service_provider_links_registered') }}
    where canonical_id is not null
),

-- Deterministic mode for display_name: the most-frequently-reported raw_name,
-- ties broken alphabetically so the value is stable across runs. (approx_top_count
-- is approximate and breaks ties arbitrarily, which can flip the display name
-- run-to-run for a human-read dim.)
name_counts as (
    select canonical_id, provider_type, raw_name, count(*) as n
    from links
    where raw_name is not null
    group by canonical_id, provider_type, raw_name
),

display_names as (
    select
        canonical_id,
        provider_type,
        array_agg(raw_name order by n desc, raw_name limit 1)[offset(0)] as display_name
    from name_counts
    group by canonical_id, provider_type
)

select
    l.canonical_id,
    l.provider_type,
    d.display_name,
    max(l.sec_number)                                            as sec_number,
    max(l.crd_number)                                            as crd_number,
    max(l.pcaob_number)                                          as pcaob_number,
    max(l.lei)                                                   as lei,
    -- city/state/country keep approx mode: it protects against a single mistyped
    -- filing (e.g. a full street address in the city field) winning, and exact
    -- determinism is not needed for these secondary fields.
    approx_top_count(l.city,    1)[safe_offset(0)].value        as city,
    approx_top_count(l.state,   1)[safe_offset(0)].value        as state,
    approx_top_count(l.country, 1)[safe_offset(0)].value        as country,
    count(distinct l.raw_name)                                  as raw_name_variants,
    array_agg(distinct l.raw_name ignore nulls order by l.raw_name limit 20) as raw_name_samples,
    count(distinct l.filing_id)                                 as total_filings_referenced
from links l
join display_names d using (canonical_id, provider_type)
group by l.canonical_id, l.provider_type, d.display_name
