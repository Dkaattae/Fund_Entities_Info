{{ config(materialized='table') }}

-- One row per (canonical_id, provider_type).
-- display_name, city, state, country all use the most-frequently-reported
-- value (mode via approx_top_count) so that a single mis-typed filing
-- (e.g. a full street address in the city field) cannot override the
-- correct value that the majority of advisers reported.

with links as (
    select * from {{ ref('int_service_provider_links') }}
    where canonical_id is not null
)

select
    canonical_id,
    provider_type,
    -- Most-common name across all filings referencing this provider
    approx_top_count(raw_name, 1)[safe_offset(0)].value         as display_name,
    max(sec_number)                                              as sec_number,
    max(crd_number)                                              as crd_number,
    max(pcaob_number)                                            as pcaob_number,
    max(lei)                                                     as lei,
    -- Most-common city/state/country to avoid stray address strings winning
    approx_top_count(city,    1)[safe_offset(0)].value          as city,
    approx_top_count(state,   1)[safe_offset(0)].value          as state,
    approx_top_count(country, 1)[safe_offset(0)].value          as country,
    count(distinct raw_name)                                     as raw_name_variants,
    array_agg(distinct raw_name ignore nulls order by raw_name limit 20) as raw_name_samples,
    count(distinct filing_id)                                    as total_filings_referenced
from links
group by canonical_id, provider_type
