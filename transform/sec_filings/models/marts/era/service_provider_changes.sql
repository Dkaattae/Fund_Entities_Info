{{ config(materialized='table') }}

-- Per (adviser, provider_type): compare current vs prior reporting year provider sets.
--
-- Reporting year = annual_amendment_fiscal_year (e.g. 2025 for an amendment filed
-- in early 2026 covering FY2025). Derived dynamically — no hardcoded years.
--
-- For each reporting year, "latest state" = the most recent filing of any type
-- (annual or other-amendment) within that reporting year. Other-amendments filed
-- after the annual amendment update the state for the same reporting year.
--
-- change_type values:
--   new_adviser   – first-ever ERA filing is in the current reporting year
--   no_prior_data – filed this year but no prior reporting year found
--   swapped       – providers added AND dropped
--   added         – net new provider(s) only
--   dropped       – provider(s) removed only (including dropped to none)
--   unchanged     – identical provider set

with base as (
    select * from {{ ref('stg_era_base') }}
),

filing_history as (
    select * from {{ ref('era_filing_history') }}
),

-- Current and prior reporting years derived from the data.
-- current_year = most recent fiscal year with annual amendment filings.
-- prior_year   = current_year - 1.
reporting_years as (
    select
        max(annual_amendment_fiscal_year)     as current_year,
        max(annual_amendment_fiscal_year) - 1 as prior_year
    from filing_history
    where is_annual_amendment_era
      and annual_amendment_fiscal_year is not null
),

-- Month name → number lookup (used for due-date filtering)
month_map as (
    select * from unnest([
        struct('JANUARY'   as month_name, 1  as month_num),
        struct('FEBRUARY'  as month_name, 2  as month_num),
        struct('MARCH'     as month_name, 3  as month_num),
        struct('APRIL'     as month_name, 4  as month_num),
        struct('MAY'       as month_name, 5  as month_num),
        struct('JUNE'      as month_name, 6  as month_num),
        struct('JULY'      as month_name, 7  as month_num),
        struct('AUGUST'    as month_name, 8  as month_num),
        struct('SEPTEMBER' as month_name, 9  as month_num),
        struct('OCTOBER'   as month_name, 10 as month_num),
        struct('NOVEMBER'  as month_name, 11 as month_num),
        struct('DECEMBER'  as month_name, 12 as month_num)
    ])
),

-- Assign other-amendments to a reporting year: inherit from the most recent
-- annual amendment for that adviser filed on or before this filing's date.
annual_anchors as (
    select
        entity_key,
        date_submitted      as annual_date,
        annual_amendment_fiscal_year as reporting_year
    from filing_history
    where is_annual_amendment_era
      and annual_amendment_fiscal_year is not null
),

filings_with_year as (
    -- Annual amendments carry their own reporting year
    select
        h.entity_key,
        h.filing_id,
        h.date_submitted,
        h.annual_amendment_fiscal_year as reporting_year
    from filing_history h
    where h.is_annual_amendment_era
      and h.annual_amendment_fiscal_year is not null

    union all

    -- Other-amendments inherit from most recent prior annual amendment
    select
        h.entity_key,
        h.filing_id,
        h.date_submitted,
        max_by(a.reporting_year, a.annual_date) as reporting_year
    from filing_history h
    join annual_anchors a
        on  a.entity_key   = h.entity_key
        and a.annual_date <= h.date_submitted
    where h.is_other_amendment_era
    group by h.entity_key, h.filing_id, h.date_submitted
),

-- Latest filing_id per (adviser, reporting_year)
latest_per_year as (
    select
        entity_key,
        reporting_year,
        max_by(filing_id, date_submitted) as filing_id,
        max(date_submitted)               as filing_date
    from filings_with_year
    group by entity_key, reporting_year
),

current_filings as (
    select l.entity_key,
           l.filing_id   as filing_id_current,
           l.filing_date as filing_date_current
    from latest_per_year l
    cross join reporting_years r
    where l.reporting_year = r.current_year
),

prior_filings as (
    select l.entity_key,
           l.filing_id   as filing_id_prior,
           l.filing_date as filing_date_prior
    from latest_per_year l
    cross join reporting_years r
    where l.reporting_year = r.prior_year
),

-- Adviser info, fiscal year end, and due date from current filing.
-- FYE month ≤ 2 (Jan/Feb): FY[N] ends in calendar year N+1.
-- FYE month ≥ 3 (Mar–Dec): FY[N] ends in calendar year N.
-- Due date = last day of FYE month + 90 days.
adviser_info as (
    select
        f.entity_key,
        b.legal_name,
        b.business_name,
        b.assets_under_management,
        b.fiscal_year_end,
        b.main_city,
        b.main_state,
        coalesce(mm.month_num, 12) as fye_month_num,
        date_add(
            last_day(date(
                r.current_year + if(coalesce(mm.month_num, 12) <= 2, 1, 0),
                coalesce(mm.month_num, 12),
                1
            )),
            interval 90 day
        ) as annual_due_date
    from current_filings f
    cross join reporting_years r
    join base b on b.filing_id = f.filing_id_current
    left join month_map mm on upper(b.fiscal_year_end) = mm.month_name
),

-- New advisers: only those whose form type is marked is_initial_sec_era.
-- Do NOT use filing_seq = 1 — that reflects position in our backfilled data,
-- not whether the adviser is genuinely new.
new_advisers as (
    select distinct entity_key
    from filing_history
    where is_initial_sec_era
),

-- Funds managed by each adviser, via ERA form_d_num → form_d_pooled_funds link.
-- An adviser may manage multiple funds; aggregate into an array.
-- Falls back gracefully when no Form D link exists (SMA-only advisers).
-- Distinct (adviser, fund) pairs first — an adviser files multiple ERA
-- amendments each reporting the same Form D numbers, causing duplicates.
adviser_fund_pairs as (
    select distinct
        coalesce(b.firm_crd, b.sec_adviser_number) as entity_key,
        f.primary_issuer_name                       as fund_name,
        f.primary_issuer_cik                        as fund_cik,
        f.file_num
    from {{ ref('stg_era_base') }} b
    join {{ source('era_adv', 'form_d_num') }} fdn using (filing_id)
    join {{ ref('form_d_pooled_funds') }} f
        on f.file_num = fdn.form_d_file_number
    where coalesce(b.firm_crd, b.sec_adviser_number) is not null
      and f.primary_issuer_name is not null
),

adviser_funds as (
    select
        entity_key,
        array_agg(
            struct(fund_name, fund_cik, file_num)
            order by fund_name
        ) as funds
    from adviser_fund_pairs
    group by entity_key
),

-- Flat provider rows for current filings — deduped per canonical provider
providers_current_flat as (
    select
        f.entity_key,
        l.provider_type,
        l.canonical_id,
        any_value(coalesce(d.display_name, l.raw_name)) as display_name
    from current_filings f
    join {{ ref('int_service_provider_links') }} l on l.filing_id = f.filing_id_current
    left join {{ ref('service_provider_dim') }}   d using (canonical_id, provider_type)
    where l.canonical_id is not null
    group by f.entity_key, l.provider_type, l.canonical_id
),

-- Flat provider rows for prior filings — deduped
providers_prior_flat as (
    select
        f.entity_key,
        l.provider_type,
        l.canonical_id,
        any_value(coalesce(d.display_name, l.raw_name)) as display_name
    from prior_filings f
    join {{ ref('int_service_provider_links') }} l on l.filing_id = f.filing_id_prior
    left join {{ ref('service_provider_dim') }}   d using (canonical_id, provider_type)
    where l.canonical_id is not null
    group by f.entity_key, l.provider_type, l.canonical_id
),

-- Full outer join to detect adds/drops per canonical provider
provider_changes_long as (
    select
        coalesce(pc.entity_key,    pp.entity_key)    as entity_key,
        coalesce(pc.provider_type, pp.provider_type) as provider_type,
        coalesce(pc.canonical_id,  pp.canonical_id)  as canonical_id,
        coalesce(pc.display_name,  pp.display_name)  as display_name,
        pc.canonical_id is not null                  as in_current,
        pp.canonical_id is not null                  as in_prior,
        case
            when pc.canonical_id is not null
             and pp.canonical_id is null     then 'added'
            when pc.canonical_id is null
             and pp.canonical_id is not null then 'dropped'
            else 'unchanged'
        end as provider_status
    from providers_current_flat pc
    full outer join providers_prior_flat pp
        on  pc.entity_key    = pp.entity_key
        and pc.provider_type = pp.provider_type
        and pc.canonical_id  = pp.canonical_id
    -- Keep only entities that filed in the current reporting year
    where coalesce(pc.entity_key, pp.entity_key) in (select entity_key from current_filings)
),

-- Aggregate per (entity, provider_type)
changes_agg as (
    select
        entity_key,
        provider_type,
        array_agg(
            case when in_current
                 then struct(canonical_id, display_name) else null end
            ignore nulls order by display_name
        ) as providers_current,
        array_agg(
            case when in_prior
                 then struct(canonical_id, display_name) else null end
            ignore nulls order by display_name
        ) as providers_prior,
        array_agg(
            case when provider_status = 'added'
                 then struct(canonical_id, display_name) else null end
            ignore nulls order by display_name
        ) as providers_added,
        array_agg(
            case when provider_status = 'dropped'
                 then struct(canonical_id, display_name) else null end
            ignore nulls order by display_name
        ) as providers_dropped,
        countif(provider_status = 'added')   as added_count,
        countif(provider_status = 'dropped') as dropped_count
    from provider_changes_long
    group by entity_key, provider_type
)

select
    c.entity_key,
    a.legal_name,
    a.business_name,
    a.assets_under_management,
    a.fiscal_year_end,
    a.main_city,
    a.main_state,
    r.current_year                                     as reporting_year,
    r.prior_year,
    cf.filing_date_current,
    pf.filing_date_prior,
    c.provider_type,

    n.entity_key is not null                           as is_new_adviser,
    pf.entity_key is null and n.entity_key is null     as has_no_prior_filing,

    coalesce(c.providers_current, [])                  as providers_current,
    coalesce(c.providers_prior,   [])                  as providers_prior,
    coalesce(c.providers_added,   [])                  as providers_added,
    coalesce(c.providers_dropped, [])                  as providers_dropped,
    a.annual_due_date,
    coalesce(af.funds, [])                             as adviser_funds,

    case
        when n.entity_key  is not null                      then 'new_adviser'
        when pf.entity_key is null                          then 'no_prior_data'
        when c.added_count > 0 and c.dropped_count > 0      then 'swapped'
        when c.added_count > 0                              then 'added'
        when c.dropped_count > 0                            then 'dropped'
        else                                                     'unchanged'
    end as change_type

from changes_agg c
cross join reporting_years r
join adviser_info    a   using (entity_key)
join current_filings cf  using (entity_key)
left join prior_filings  pf  using (entity_key)
left join new_advisers   n   using (entity_key)
left join adviser_funds  af  using (entity_key)
where current_date() >= a.annual_due_date   -- exclude advisers not yet past their due date
order by a.assets_under_management desc nulls last, a.legal_name
