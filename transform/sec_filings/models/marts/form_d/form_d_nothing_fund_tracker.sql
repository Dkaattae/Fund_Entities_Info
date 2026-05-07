{{ config(materialized='table') }}

-- "Nothing funds" — pooled investment funds that:
--   1. Filed their initial Form D with $0 raised and first sale yet to occur
--   2. Have no shared related persons with any other fund (no institutional trail)
--   3. Initial filing on or after 2025-01-01
--
-- Tracks each fund's fundraising velocity = latest total_amount_sold / days since initial.
-- Broken down by adviser cohort (ERA / state / none) and investor type (institutional / individual).
--
-- Velocity = null for funds still at $0. has_raised = false for those still waiting.

with funds as (
    select * from {{ ref('form_d_pooled_funds') }}
),

-- Day 0: earliest non-amendment filing per file_num
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

-- Shared person check: funds whose related persons appear in any OTHER fund
related_by_fund as (
    select distinct
        f.file_num,
        rp.full_name
    from {{ ref('stg_form_d_related_persons') }} rp
    join funds f using (accession_number)
    where f.file_num is not null
),

funds_with_shared_persons as (
    select distinct r1.file_num
    from related_by_fund r1
    join related_by_fund r2
        on  r1.full_name = r2.full_name
        and r1.file_num  != r2.file_num
),

-- Latest fundraising state per fund (from most recent amendment)
latest_per_fund as (
    select
        file_num,
        max(filing_date)                       as latest_filing_date,
        max_by(total_amount_sold, filing_date) as latest_total_amount_sold
    from funds
    where file_num is not null
    group by file_num
),

-- Dimensions taken from the initial filing (stable cohort classification)
initial_dims as (
    select
        f.accession_number,
        f.primary_issuer_cik,
        f.primary_issuer_name,
        f.primary_issuer_state,
        f.entity_type,
        f.investment_fund_type,
        f.claims_3c1,
        f.claims_3c7,
        f.claims_506b,
        f.claims_506c,
        f.total_amount_sold       as initial_amount_sold,
        f.first_sale_yet_to_occur,
        f.edgar_fund_history_url
    from funds f
),

-- Adviser cohort (same logic as form_d_first_raise)
adviser as (
    select * from {{ ref('int_form_d_adviser_link') }}
),

era_aum as (
    select entity_key, assets_under_management as adviser_aum
    from {{ ref('era_latest_filing') }}
),

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
    d.edgar_fund_history_url,

    -- Investor type: 3c7 = institutional (qualified purchasers only)
    --               3c1 = individual (accredited investors, up to 100)
    case
        when d.claims_3c7 then 'institutional'
        when d.claims_3c1 then 'individual'
        else                   'other'
    end as investor_type,

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

    -- Latest fundraising state
    l.latest_filing_date,
    coalesce(l.latest_total_amount_sold, 0)         as latest_total_amount_sold,
    coalesce(l.latest_total_amount_sold, 0) > 0     as has_raised,

    date_diff(l.latest_filing_date, i.initial_filing_date, day) as days_since_initial,

    -- Velocity: $ per day. Null for funds still at $0.
    case
        when coalesce(l.latest_total_amount_sold, 0) > 0
         and date_diff(l.latest_filing_date, i.initial_filing_date, day) > 0
        then l.latest_total_amount_sold
             / date_diff(l.latest_filing_date, i.initial_filing_date, day)
    end as raising_velocity,

    -- Adviser cohort (mirrors form_d_first_raise)
    case
        when adv.adviser_entity_key is null
            then 'no_adviser'
        when not coalesce(es.is_also_state_registered, false)
            then case
                when coalesce(ea.adviser_aum, 0) > {{ var('adviser_aum_threshold', 100000000) }}
                    then 'era_big'
                else 'era_small'
            end
        when coalesce(es.state_registration_count, 0) > 1
            then case
                when coalesce(ea.adviser_aum, 0) > {{ var('adviser_aum_threshold', 100000000) }}
                    then 'multi_state_big'
                else 'multi_state_small'
            end
        else
            case
                when coalesce(ea.adviser_aum, 0) > {{ var('adviser_aum_threshold', 100000000) }}
                    then 'single_state_big'
                else 'single_state_small'
            end
    end as adviser_cohort,

    ea.adviser_aum,
    adv.adviser_legal_name,
    adv.adviser_entity_key

from initial_filings i
join latest_per_fund l  using (file_num)
join initial_dims d     on d.accession_number = i.initial_accession_number
-- Exclude funds with any shared related-person connection
left join funds_with_shared_persons sp using (file_num)
left join adviser adv   on adv.accession_number = i.initial_accession_number
left join era_aum  ea   on ea.entity_key = adv.adviser_entity_key
left join era_state es  on es.entity_key = adv.adviser_entity_key

where coalesce(d.initial_amount_sold, 0) = 0
  and d.first_sale_yet_to_occur = true
  and sp.file_num is null                -- no shared person connections
  and i.initial_filing_date >= '2024-01-01'
order by raising_velocity desc nulls last
