{{ config(materialized='table') }}

-- Per fund offering (file_num): the first moment total_amount_sold > 0,
-- plus the duration from the initial Form D to that first raise.
--
-- Dimensions are taken from the initial (non-amendment) filing so cohorts
-- are stable — they reflect what the fund looked like on day 0, not after
-- amendments may have changed investment_fund_type etc.
--
-- adviser_cohort classifies the linked ERA adviser into six buckets:
--   era_big / era_small            – SEC-exempt reporter, not state-registered
--   multi_state_big / _small       – registered in 2+ states
--   single_state_big / _small      – registered in exactly 1 state
-- "big" = adviser AUM above {{ var('adviser_aum_threshold', 100000000) }} (default $100M)
--
-- Scoped to funds whose initial Form D was on or after 2025-01-01.
-- Only funds that have actually raised (total_amount_sold > 0) appear here.

with funds as (
    select * from {{ ref('form_d_pooled_funds') }}
),

-- Earliest non-amendment filing per file_num — this is "day 0"
initial_filings as (
    select
        file_num,
        min_by(accession_number, filing_date) as initial_accession_number,
        min(filing_date)                       as initial_filing_date
    from funds
    where is_amendment_submission = false
      and file_num is not null
    group by file_num
),

-- First filing where total_amount_sold crosses above 0.
-- first_raise_date = sale_date from that filing (actual date of first sale,
-- not the filing submission date which can lag by months).
first_raise as (
    select
        file_num,
        min_by(sale_date,         filing_date) as first_raise_date,
        min_by(total_amount_sold, filing_date) as first_raise_amount
    from funds
    where total_amount_sold > 0
      and file_num is not null
    group by file_num
),

-- Shared related-person connections: count of other pooled funds that share
-- at least one named related person with the initial filing of this fund.
shared_connections as (
    select
        rp1.accession_number,
        count(distinct f2.file_num) as shared_fund_count
    from {{ ref('stg_form_d_related_persons') }} rp1
    join {{ ref('stg_form_d_related_persons') }} rp2
        on  rp1.full_name        = rp2.full_name
        and rp1.accession_number != rp2.accession_number
    join {{ ref('form_d_pooled_funds') }} f2
        on rp2.accession_number = f2.accession_number
    group by rp1.accession_number
),

adviser as (
    select * from {{ ref('int_form_d_adviser_link') }}
),

-- ERA adviser AUM from their most recent filing
era_aum as (
    select entity_key, assets_under_management as adviser_aum
    from {{ ref('era_latest_filing') }}
),

-- State registration status: is the ERA adviser also state-registered,
-- and in how many states?
era_state as (
    select entity_key, is_also_state_registered, state_registration_count
    from {{ ref('era_state_registration_status') }}
)

select
    i.file_num,
    d.primary_issuer_cik,
    d.primary_issuer_name,
    d.primary_issuer_state,
    d.entity_type,
    d.investment_fund_type,

    -- 3c1/3c7 = who can invest; 506b/506c = how you can solicit — orthogonal
    case
        when d.claims_3c7 then '3c7'
        when d.claims_3c1 then '3c1'
        else                   'other'
    end as investor_exemption,
    case
        when d.claims_506c then '506c'
        when d.claims_506b then '506b'
        else                    'other'
    end as offering_exemption,

    i.initial_filing_date,
    date_trunc(i.initial_filing_date, quarter)     as initial_filing_quarter,
    format_date('%Y-Q%Q', i.initial_filing_date)   as initial_filing_quarter_label,

    r.first_raise_date,
    r.first_raise_amount,
    greatest(date_diff(r.first_raise_date, i.initial_filing_date, day), 0) as days_to_first_raise,

    -- Was the adviser already active before this fund filed?
    case
        when adv.adviser_entity_key is null                             then 'no_adviser'
        when adv.adviser_first_adv_filing_date < i.initial_filing_date then 'established_manager'
        else                                                                 'new_manager'
    end as manager_type,

    -- Adviser cohort: registration type × AUM size
    -- ERA = pure exempt reporter (not state-registered)
    -- multi_state / single_state = also holds state registration(s)
    case
        when adv.adviser_entity_key is null
            then 'no_adviser'

        when not coalesce(es.is_also_state_registered, false)
            -- SEC-exempt reporter only
            then case
                when coalesce(ea.adviser_aum, 0) > {{ var('adviser_aum_threshold', 100000000) }}
                    then 'era_big'
                else 'era_small'
            end

        when coalesce(es.state_registration_count, 0) > 1
            -- Registered in multiple states
            then case
                when coalesce(ea.adviser_aum, 0) > {{ var('adviser_aum_threshold', 100000000) }}
                    then 'multi_state_big'
                else 'multi_state_small'
            end

        else
            -- Registered in exactly one state
            case
                when coalesce(ea.adviser_aum, 0) > {{ var('adviser_aum_threshold', 100000000) }}
                    then 'single_state_big'
                else 'single_state_small'
            end
    end as adviser_cohort,

    ea.adviser_aum,
    es.state_registration_count              as adviser_state_registration_count,
    adv.adviser_legal_name,
    adv.adviser_entity_key,
    coalesce(sc.shared_fund_count, 0)        as shared_fund_count

from initial_filings i
join first_raise r        using (file_num)
join funds d              on d.accession_number  = i.initial_accession_number
left join adviser adv     on adv.accession_number = i.initial_accession_number
left join era_aum  ea     on ea.entity_key        = adv.adviser_entity_key
left join era_state es    on es.entity_key        = adv.adviser_entity_key
left join shared_connections sc on sc.accession_number = i.initial_accession_number
where i.initial_filing_date >= '2024-01-01'
order by r.first_raise_amount desc nulls last
