{{ config(materialized='table') }}

-- Cleaned Form D filings, scoped to the Pooled Investment Fund industry
-- group. Exemption flags are surfaced for downstream filtering — no
-- threshold filter is applied here.

select
    accession_number,
    file_num,
    filing_date,
    submission_type,
    is_amendment_submission,

    primary_issuer_cik,
    primary_issuer_name,
    primary_issuer_state,
    jurisdiction_of_inc,
    entity_type,
    year_of_inc_choice,
    year_of_inc,

    investment_fund_type,
    aggregate_nav_range,
    sale_date,
    first_sale_yet_to_occur,
    minimum_investment_accepted,
    total_offering_amount_raw,
    total_offering_amount_numeric,
    total_amount_sold,
    total_remaining_numeric,

    -- EDGAR links
    edgar_filing_url,
    edgar_fund_history_url,

    -- Exemption flags
    claims_3c1,
    claims_3c7,
    claims_506b,
    claims_506c,

    -- Small / emerging proxies
    has_under_100_persons,
    over_100_recipients,
    has_non_accredited_investors_flag,
    number_non_accredited_investors,
    number_already_invested,
    low_minimum_investment_flag

from {{ ref('int_form_d_filings') }}
where is_pooled_investment_fund
