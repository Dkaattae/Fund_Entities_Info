{{ config(materialized='table') }}

-- One row per (entity_key, reporting_year): the fully-reconstructed state for that
-- fiscal year.
--
-- ADV amendments are sparse: an amendment carries only the fields the filer changed.
-- A field left blank in a later amendment means "unchanged", NOT "now empty". So a
-- year's state cannot be read from latest_filing_id alone — when the latest filing for
-- a year is an other-amendment that omitted AUM (or the fund schedule), that field
-- would read as null/empty and produce false closure signals downstream.
--
-- Instead, for each (entity, reporting_year) we reconstruct each field from the year's
-- filing chain (the annual baseline + every same-year other-amendment, ordered by
-- date_submitted):
--   * assets_under_management: the most recent NON-NULL value in the chain.
--   * fund_file_numbers:       the fund list from the most recent filing in the chain
--                              that reported >= 1 fund (a filing with zero fund rows
--                              left the schedule untouched, so we fall back to the last
--                              filing that did report funds).
--
-- AUM is reconstructed only within the reporting year, never carried across years, so a
-- genuine year-over-year drop to zero remains detectable downstream.

with year_map as (
    select * from {{ ref('int_era_filing_year_map') }}
),

by_year as (
    select * from {{ ref('int_era_filings_by_year') }}
),

hist as (
    select filing_id, assets_under_management
    from {{ ref('era_filing_history') }}
),

-- Form D file numbers disclosed in a given filing
fund_links as (
    select filing_id, form_d_file_number
    from {{ source('era_adv', 'form_d_num') }}
    where form_d_file_number is not null
),

-- ── AUM: most recent non-null value across the year's filing chain ──────────
chain_aum as (
    select
        ym.entity_key,
        ym.reporting_year,
        array_agg(h.assets_under_management ignore nulls
                  order by ym.date_submitted desc, ym.filing_id desc
                  limit 1)[safe_offset(0)] as assets_under_management
    from year_map ym
    join hist h on h.filing_id = ym.filing_id
    group by ym.entity_key, ym.reporting_year
),

-- ── Funds: the most recent filing in the chain that actually listed funds ───
chain_fund_counts as (
    select
        ym.entity_key,
        ym.reporting_year,
        ym.filing_id,
        ym.date_submitted,
        count(fl.form_d_file_number) as n_funds
    from year_map ym
    left join fund_links fl on fl.filing_id = ym.filing_id
    group by ym.entity_key, ym.reporting_year, ym.filing_id, ym.date_submitted
),

fund_source as (
    select
        entity_key,
        reporting_year,
        max_by(filing_id, date_submitted) as fund_filing_id
    from chain_fund_counts
    where n_funds > 0
    group by entity_key, reporting_year
),

fund_list as (
    select
        fs.entity_key,
        fs.reporting_year,
        array_agg(fl.form_d_file_number order by fl.form_d_file_number) as fund_file_numbers,
        count(fl.form_d_file_number)                                    as fund_count
    from fund_source fs
    join fund_links fl on fl.filing_id = fs.fund_filing_id
    group by fs.entity_key, fs.reporting_year
)

select
    b.entity_key,
    b.reporting_year,
    b.annual_filing_id,
    b.annual_filing_date,
    b.latest_filing_id,
    b.latest_filing_date,
    b.is_superseded_by_amendment,
    ca.assets_under_management,
    -- Array of Form D file numbers as of this fiscal year (latest filing that
    -- reported any). NULL when the adviser never reported funds in this year's chain.
    fl.fund_file_numbers,
    coalesce(fl.fund_count, 0) as fund_count
from by_year b
left join chain_aum  ca using (entity_key, reporting_year)
left join fund_list  fl using (entity_key, reporting_year)
order by b.entity_key, b.reporting_year
