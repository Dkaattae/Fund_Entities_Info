{{ config(materialized='table') }}

-- Per primary issuer CIK: the full Form D filing history plus capital raised.
--
-- IMPORTANT: amendments report cumulative `total_amount_sold` for an offering.
-- Naive SUM across all rows would double-count. Per-offering (file_num)
-- we take the LATEST filing's value, then SUM across distinct offerings of
-- the same issuer.

with funds as (
    select * from {{ ref('form_d_pooled_funds') }}
),

per_offering_latest as (
    select
        primary_issuer_cik,
        file_num,
        primary_issuer_name,
        max(filing_date)                                          as latest_filing_date,
        max_by(total_amount_sold, filing_date)                    as latest_total_amount_sold,
        max_by(total_offering_amount_numeric, filing_date)        as latest_total_offering_amount,
        min(filing_date)                                          as first_filing_date,
        count(*)                                                  as filings_in_offering
    from funds
    where primary_issuer_cik is not null
    group by primary_issuer_cik, file_num, primary_issuer_name
),

per_issuer_agg as (
    select
        primary_issuer_cik,
        any_value(primary_issuer_name)            as primary_issuer_name,
        count(distinct file_num)                  as distinct_offerings,
        sum(filings_in_offering)                  as total_filings,
        min(first_filing_date)                    as first_filing_date,
        max(latest_filing_date)                   as latest_filing_date,
        sum(coalesce(latest_total_amount_sold, 0))   as total_capital_raised,
        sum(coalesce(latest_total_offering_amount, 0)) as total_offering_amount,
        array_agg(struct(
            file_num,
            first_filing_date,
            latest_filing_date,
            filings_in_offering,
            latest_total_amount_sold,
            latest_total_offering_amount
        ) order by latest_filing_date desc) as offerings
    from per_offering_latest
    group by primary_issuer_cik
)

select
    primary_issuer_cik,
    primary_issuer_name,
    distinct_offerings,
    total_filings,
    first_filing_date,
    latest_filing_date,
    total_capital_raised,
    total_offering_amount,
    offerings
from per_issuer_agg
order by total_capital_raised desc
