{{ config(materialized='table', tags=['era']) }}

-- Year-over-year adviser count per service provider, bucketed by fiscal year.
--
-- Filing resolution: uses int_era_annual_snapshot.latest_filing_id per
-- (entity_key, reporting_year) so that other-amendments filed after the annual
-- amendment are reflected in the count. Previously this joined directly to
-- era_filing_history filtered to is_annual_amendment_era, which ignored
-- provider changes reported in subsequent other-amendments.

with links as (
    select * from {{ ref('int_service_provider_links_registered') }}
    where canonical_id is not null
),

-- One row per (entity_key, fiscal_year) with the latest filing_id for that year.
-- latest_filing_id = annual_filing_id unless a later other-amendment supersedes it.
snapshot as (
    select
        entity_key,
        reporting_year as fiscal_year,
        latest_filing_id as filing_id
    from {{ ref('int_era_annual_snapshot') }}
),

-- After March the prior year's filing season is complete; use it as "this year".
-- On/before March we are still in filing season so the max year is current.
current_fy as (
    select
        case
            when extract(month from current_date()) > 3
                then max(fiscal_year) - 1
            else max(fiscal_year)
        end as yr
    from snapshot
),

provider_filings as (
    select
        l.canonical_id,
        l.provider_type,
        s.entity_key,
        s.fiscal_year
    from links l
    join snapshot s on s.filing_id = l.filing_id
),

counts as (
    select
        canonical_id,
        provider_type,
        fiscal_year,
        count(distinct entity_key) as adviser_count
    from provider_filings
    group by canonical_id, provider_type, fiscal_year
),

pivoted as (
    select
        canonical_id,
        provider_type,
        max(case when fiscal_year = (select yr from current_fy)
                 then adviser_count end) as count_this_year,
        max(case when fiscal_year = (select yr from current_fy) - 1
                 then adviser_count end) as count_last_year,
        (select yr from current_fy) as report_year
    from counts
    group by canonical_id, provider_type
)

select
    p.canonical_id,
    p.provider_type,
    d.display_name,
    d.city,
    d.state,
    d.country,
    p.report_year,
    coalesce(p.count_this_year, 0) as count_this_year,
    coalesce(p.count_last_year, 0) as count_last_year,
    case
        when coalesce(p.count_last_year, 0) = 0 then null
        else round(
            (coalesce(p.count_this_year, 0) - coalesce(p.count_last_year, 0))
            * 100.0 / coalesce(p.count_last_year, 0),
            1
        )
    end as pct_change
from pivoted p
left join {{ ref('service_provider_dim') }} d using (canonical_id, provider_type)
order by p.provider_type, coalesce(p.count_this_year, 0) desc
