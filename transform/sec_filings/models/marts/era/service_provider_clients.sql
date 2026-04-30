{{ config(materialized='table') }}

-- For each service provider (canonical_id) and provider_type, list the ERAs
-- they served in the current calendar year. "Current year" = max year of
-- date_submitted across the ERA base table (so the model is meaningful even
-- when "today" runs ahead of the latest available filing month).

with links as (
    select * from {{ ref('int_service_provider_links') }}
    where canonical_id is not null
),

base as (
    select * from {{ ref('stg_era_base') }}
),

current_year as (
    select extract(year from max(date_submitted)) as yr from base
),

base_with_year as (
    select
        b.filing_id,
        coalesce(b.firm_crd, b.sec_adviser_number) as entity_key,
        b.firm_crd,
        b.sec_adviser_number,
        b.legal_name,
        b.business_name,
        b.date_submitted,
        b.assets_under_management,
        extract(year from b.date_submitted) as filing_year
    from base b
),

current_year_filings as (
    select b.*
    from base_with_year b
    cross join current_year c
    where b.filing_year = c.yr
),

joined as (
    select
        l.canonical_id,
        l.provider_type,
        f.entity_key,
        f.firm_crd,
        f.sec_adviser_number,
        f.legal_name,
        f.business_name,
        f.assets_under_management,
        f.date_submitted,
        f.filing_id
    from links l
    join current_year_filings f using (filing_id)
),

-- Latest filing per (provider, client) so each client appears once
client_latest as (
    select
        canonical_id,
        provider_type,
        entity_key,
        max(firm_crd) as firm_crd,
        max(sec_adviser_number) as sec_adviser_number,
        max(legal_name) as client_legal_name,
        max(business_name) as client_business_name,
        max(date_submitted) as latest_date_submitted,
        max(assets_under_management) as latest_aum
    from joined
    group by canonical_id, provider_type, entity_key
),

agg as (
    select
        canonical_id,
        provider_type,
        count(distinct entity_key) as client_count,
        sum(latest_aum)            as total_client_aum,
        array_agg(struct(
            entity_key,
            client_legal_name,
            firm_crd,
            sec_adviser_number,
            latest_aum,
            latest_date_submitted
        ) order by latest_aum desc nulls last limit 200) as clients
    from client_latest
    group by canonical_id, provider_type
)

select
    a.canonical_id,
    a.provider_type,
    d.display_name,
    d.sec_number,
    d.pcaob_number,
    d.lei,
    d.city,
    d.state,
    d.country,
    (select yr from current_year) as report_year,
    a.client_count,
    a.total_client_aum,
    a.clients
from agg a
left join {{ ref('service_provider_dim') }} d using (canonical_id, provider_type)
order by a.client_count desc
