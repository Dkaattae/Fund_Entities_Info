{{ config(materialized='table', tags=['era']) }}

-- Year-over-year adviser count per service provider, bucketed by fiscal year.
-- "Fiscal year" = annual_amendment_fiscal_year from era_filing_history.
-- e.g. a firm with FYE 3/31/2026 filing in April 2026 is counted in FY 2025.
-- Only annual-amendment ERA filings are considered — those are the ones where
-- advisers formally report their service providers.

with links as (
    select * from {{ ref('int_service_provider_links') }}
    where canonical_id is not null
),

filing_history as (
    select
        filing_id,
        entity_key,
        fiscal_year
    from {{ ref('era_filing_history') }}
    where is_annual_amendment_era = true
      and fiscal_year is not null
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
    from filing_history
),

provider_filings as (
    select
        l.canonical_id,
        l.provider_type,
        f.entity_key,
        f.fiscal_year
    from links l
    join filing_history f using (filing_id)
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
