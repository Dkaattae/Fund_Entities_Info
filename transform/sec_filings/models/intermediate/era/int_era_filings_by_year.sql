{{ config(materialized='table') }}

-- One row per (entity_key, reporting_year).
-- reporting_year = annual_amendment_fiscal_year from the annual amendment.
-- Other-amendments are assigned to the reporting year of the most recent prior annual.
-- latest_filing_id is the most recent amendment of any type within that year;
-- it equals annual_filing_id unless an other-amendment was filed after the annual.

with history as (
    select * from {{ ref('era_filing_history') }}
),

annuals as (
    select
        entity_key,
        filing_id      as annual_filing_id,
        date_submitted as annual_filing_date,
        fiscal_year    as reporting_year
    from history
    where is_annual_amendment_era
      and fiscal_year is not null
),

-- Other-amendments inherit the reporting year of the most recent prior annual
other_amendments as (
    select
        h.entity_key,
        h.filing_id,
        h.date_submitted,
        max_by(a.reporting_year, a.annual_filing_date) as reporting_year
    from history h
    join annuals a
        on  a.entity_key         = h.entity_key
        and a.annual_filing_date <= h.date_submitted
    where h.is_other_amendment_era
    group by h.entity_key, h.filing_id, h.date_submitted
),

all_with_year as (
    select entity_key, annual_filing_id as filing_id, annual_filing_date as date_submitted, reporting_year
    from annuals
    union all
    select entity_key, filing_id, date_submitted, reporting_year
    from other_amendments
),

latest_per_year as (
    select
        entity_key,
        reporting_year,
        max_by(filing_id, date_submitted) as latest_filing_id,
        max(date_submitted)               as latest_filing_date
    from all_with_year
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
