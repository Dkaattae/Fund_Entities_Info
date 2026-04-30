{{ config(materialized='table') }}

-- One row per (canonical_id, provider_type). Picks the most-recent raw_name
-- as the display name, plus aggregated identifiers and address.

with links as (
    select * from {{ ref('int_service_provider_links') }}
    where canonical_id is not null
),

ranked as (
    select
        canonical_id,
        provider_type,
        raw_name,
        sec_number,
        crd_number,
        pcaob_number,
        lei,
        city,
        state,
        country,
        filing_month,
        row_number() over (
            partition by canonical_id, provider_type
            order by filing_month desc, raw_name
        ) as rn
    from links
),

display as (
    select
        canonical_id,
        provider_type,
        raw_name as display_name
    from ranked
    where rn = 1
),

agg as (
    select
        canonical_id,
        provider_type,
        max(sec_number)   as sec_number,
        max(crd_number)   as crd_number,
        max(pcaob_number) as pcaob_number,
        max(lei)          as lei,
        max(city)         as city,
        max(state)        as state,
        max(country)      as country,
        count(distinct raw_name) as raw_name_variants,
        array_agg(distinct raw_name ignore nulls order by raw_name limit 20) as raw_name_samples,
        count(distinct filing_id) as total_filings_referenced
    from links
    group by canonical_id, provider_type
)

select
    a.canonical_id,
    a.provider_type,
    d.display_name,
    a.sec_number,
    a.crd_number,
    a.pcaob_number,
    a.lei,
    a.city,
    a.state,
    a.country,
    a.raw_name_variants,
    a.raw_name_samples,
    a.total_filings_referenced
from agg a
join display d using (canonical_id, provider_type)
