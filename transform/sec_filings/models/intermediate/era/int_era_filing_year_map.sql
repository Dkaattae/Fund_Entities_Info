{{ config(materialized='view') }}

-- Per-filing → reporting_year assignment: the building block for year-level
-- reconstruction. One row per ERA filing that belongs to a reporting year.
--
--   * Annual amendments define a reporting year (their derived fiscal_year).
--   * Other-amendments inherit the reporting year of the most recent prior annual
--     for the same entity — they are patches applied on top of that annual.
--
-- Both int_era_filings_by_year (latest filing per year) and int_era_annual_snapshot
-- (field-level reconstruction across a year's filing chain) build on this, so the
-- year-assignment logic lives in exactly one place.

with history as (
    select * from {{ ref('era_filing_history') }}
),

annuals as (
    select
        entity_key,
        filing_id      as filing_id,
        date_submitted as date_submitted,
        fiscal_year    as reporting_year
    from history
    where is_annual_amendment_era
      and fiscal_year is not null
),

-- Other-amendments inherit the reporting year of the most recent prior annual.
other_amendments as (
    select
        h.entity_key,
        h.filing_id,
        h.date_submitted,
        max_by(a.reporting_year, a.date_submitted) as reporting_year
    from history h
    join annuals a
        on  a.entity_key      = h.entity_key
        and a.date_submitted <= h.date_submitted
    where h.is_other_amendment_era
    group by h.entity_key, h.filing_id, h.date_submitted
)

select entity_key, filing_id, date_submitted, reporting_year, true  as is_annual
from annuals
union all
select entity_key, filing_id, date_submitted, reporting_year, false as is_annual
from other_amendments
