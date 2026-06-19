{{ config(materialized='table') }}

-- One row per (entity_key, reporting_year): the fully-resolved state for that
-- fiscal year, joining int_era_filings_by_year to the actual content from
-- latest_filing_id (annual amendment + any subsequent other-amendments).
--
-- "latest" means: if an adviser filed their FY 2024 annual in January 2025 and
-- then amended it in March 2025, the March 2025 amendment's fund list and AUM
-- are what this snapshot carries for reporting_year = 2024.
--
-- Downstream consumers (era_fund_closures, etc.) should use this rather than
-- comparing consecutive raw filings, which conflates other-amendments with
-- annual amendments and produces false-positive closure signals.

with by_year as (
    select * from {{ ref('int_era_filings_by_year') }}
),

filing_aum as (
    select filing_id, assets_under_management
    from {{ ref('era_filing_history') }}
),

-- Form D file numbers disclosed in a given filing.
-- DISTINCT because form_d_num can carry several rows per (filing, fund)
-- (one per reference_id); without it the fund array and fund_count double-count.
fund_links as (
    select distinct
        filing_id,
        form_d_file_number
    from {{ source('era_adv', 'form_d_num') }}
    where form_d_file_number is not null
)

select
    b.entity_key,
    b.reporting_year,
    b.annual_filing_id,
    b.annual_filing_date,
    b.latest_filing_id,
    b.latest_filing_date,
    b.is_superseded_by_amendment,
    a.assets_under_management,
    -- Array of Form D file numbers from the latest filing for this year.
    -- NULL when the adviser reported no funds (no form_d_num rows for that filing).
    array_agg(fl.form_d_file_number ignore nulls order by fl.form_d_file_number)
        as fund_file_numbers,
    count(fl.form_d_file_number) as fund_count
from by_year b
left join filing_aum  a  on a.filing_id  = b.latest_filing_id
left join fund_links  fl on fl.filing_id = b.latest_filing_id
group by
    b.entity_key,
    b.reporting_year,
    b.annual_filing_id,
    b.annual_filing_date,
    b.latest_filing_id,
    b.latest_filing_date,
    b.is_superseded_by_amendment,
    a.assets_under_management
