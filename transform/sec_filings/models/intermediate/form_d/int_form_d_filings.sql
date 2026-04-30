{{ config(materialized='view') }}

-- One row per Form D filing (accession_number) with submission + offering +
-- the primary issuer flattened together. Adds derived flags used by the
-- downstream marts.

with submission as (
    select * from {{ ref('stg_form_d_submission') }}
),

offering as (
    select * from {{ ref('stg_form_d_offering') }}
),

issuer as (
    select * from {{ ref('stg_form_d_issuer') }}
),

primary_issuer as (
    select
        accession_number,
        cik                            as primary_issuer_cik,
        entity_name                    as primary_issuer_name,
        city                           as primary_issuer_city,
        state_or_country               as primary_issuer_state,
        state_or_country_description   as primary_issuer_state_desc,
        jurisdiction_of_inc            as jurisdiction_of_inc,
        entity_type                    as entity_type,
        year_of_inc_choice             as year_of_inc_choice,
        year_of_inc                    as year_of_inc
    from issuer
    where is_primary_issuer
    qualify row_number() over (partition by accession_number order by issuer_seq_key) = 1
)

select
    s.accession_number,
    s.file_num,
    s.filing_date,
    s.submission_type,
    s.is_amendment_submission,
    s.over_100_persons,
    s.over_100_issuers,

    pi.primary_issuer_cik,
    pi.primary_issuer_name,
    pi.primary_issuer_city,
    pi.primary_issuer_state,
    pi.primary_issuer_state_desc,
    pi.jurisdiction_of_inc,
    pi.entity_type,
    pi.year_of_inc_choice,
    pi.year_of_inc,

    o.industry_group_type,
    o.investment_fund_type,
    o.aggregate_nav_range,
    o.is_amendment                       as offering_is_amendment,
    o.previous_accession_number,
    o.sale_date,
    o.first_sale_yet_to_occur,
    o.minimum_investment_accepted,
    o.over_100_recipients,
    o.total_offering_amount_raw,
    o.total_offering_amount_numeric,
    o.total_amount_sold,
    o.total_remaining_numeric,
    o.has_non_accredited_investors,
    o.number_non_accredited_investors,
    o.number_already_invested,
    o.sales_commission_amount,
    o.finders_fee_amount,
    o.gross_proceeds_used_amount,

    o.claims_3c1,
    o.claims_3c7,
    o.claims_506b,
    o.claims_506c,

    -- Derived "small / emerging" proxies (no thresholds applied — flags only)
    o.industry_group_type = 'Pooled Investment Fund'        as is_pooled_investment_fund,
    not s.over_100_persons                                  as has_under_100_persons,
    o.has_non_accredited_investors                          as has_non_accredited_investors_flag,
    coalesce(o.minimum_investment_accepted, 0) <= 100000    as low_minimum_investment_flag
from submission s
left join offering        o  using (accession_number)
left join primary_issuer  pi using (accession_number)
