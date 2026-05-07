{{ config(materialized='table') }}

-- Count of initial (non-amendment) pooled investment fund Form D filings,
-- one row per (quarter, fund_type).
-- Scoped to filing_date >= 2025-01-01 to match the ingestion backfill floor.

select
    date_trunc(filing_date, quarter)          as filing_quarter,
    format_date('%Y-Q%Q', filing_date)        as quarter_label,
    coalesce(investment_fund_type, 'Unknown') as fund_type,
    count(*)                                  as fund_count

from {{ ref('form_d_pooled_funds') }}
where is_amendment_submission = false
  and filing_date >= '2024-01-01'
  and filing_date is not null
group by filing_quarter, quarter_label, fund_type
order by filing_quarter, fund_type
