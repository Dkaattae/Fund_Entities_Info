{{ config(materialized='table') }}

-- One row per (entity_key, reporting_year).
-- reporting_year = annual_amendment_fiscal_year from the annual amendment.
-- Other-amendments are assigned to the reporting year of the most recent prior annual
-- (see int_era_filing_year_map).
-- latest_filing_id is the most recent filing of any type within that year;
-- it equals annual_filing_id unless an other-amendment was filed after the annual.

with year_map as (
    select * from {{ ref('int_era_filing_year_map') }}
),

-- Latest annual per (entity, reporting_year). Defends against a re-filed annual
-- for the same fiscal year by collapsing to the most recent one.
annuals as (
    select
        entity_key,
        reporting_year,
        max_by(filing_id, date_submitted) as annual_filing_id,
        max(date_submitted)               as annual_filing_date
    from year_map
    where is_annual
    group by entity_key, reporting_year
),

latest_per_year as (
    select
        entity_key,
        reporting_year,
        max_by(filing_id, date_submitted) as latest_filing_id,
        max(date_submitted)               as latest_filing_date
    from year_map
    group by entity_key, reporting_year
)

select
    l.entity_key,
    l.reporting_year,
    a.annual_filing_id,
    a.annual_filing_date,
    l.latest_filing_id,
    l.latest_filing_date,
    l.latest_filing_id != a.annual_filing_id as is_superseded_by_amendment
from latest_per_year l
join annuals a using (entity_key, reporting_year)
order by entity_key, reporting_year
