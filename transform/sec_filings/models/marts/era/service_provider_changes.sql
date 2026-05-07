{{ config(materialized='table') }}

-- Per (adviser, provider_type): compare the two most recent filings for each entity.
-- "Current" = most recent filing of any type (annual or other-amendment).
-- "Prior"   = the filing immediately before it in submission-date order.
--
-- This naturally handles both comparison cases:
--   - Latest is an annual    → prior is typically the prior year's latest amendment
--   - Latest is an amendment → prior is the annual (or amendment) it supersedes
--
-- change_type values:
--   new_adviser   – adviser's first-ever ERA filing (is_initial_sec_era)
--   no_prior_data – has a current filing but no prior one
--   swapped       – providers added AND dropped
--   added         – net new provider(s) only
--   dropped       – provider(s) removed only
--   unchanged     – identical provider set between the two filings

with filing_history as (
    select * from {{ ref('era_filing_history') }}
),

-- Rank all filings per entity, most recent first
ranked as (
    select *,
        row_number() over (
            partition by entity_key
            order by date_submitted desc nulls last, filing_id desc
        ) as rn
    from filing_history
),

current_filings as (
    select entity_key,
           filing_id      as filing_id_current,
           date_submitted as filing_date_current
    from ranked
    where rn = 1
),

prior_filings as (
    select entity_key,
           filing_id      as filing_id_prior,
           date_submitted as filing_date_prior
    from ranked
    where rn = 2
),

-- Adviser display info pulled from current filing
adviser_info as (
    select
        cf.entity_key,
        b.legal_name,
        b.business_name,
        b.assets_under_management,
        b.fiscal_year_end,
        b.main_city,
        b.main_state,
        case when b.firm_crd is not null
            then concat('https://www.adviserinfo.sec.gov/Firm/', b.firm_crd)
        end as iapd_url
    from current_filings cf
    join {{ ref('stg_era_base') }} b on b.filing_id = cf.filing_id_current
),

-- New advisers: those whose form type is marked is_initial_sec_era
new_advisers as (
    select distinct entity_key
    from filing_history
    where is_initial_sec_era
),

-- Funds managed by each adviser via ERA form_d_num → form_d_pooled_funds link
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

-- Flat provider rows for current filings, deduped per canonical provider
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

-- Flat provider rows for prior filings, deduped
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
            else                                  'unchanged'
        end as provider_status
    from providers_current_flat pc
    full outer join providers_prior_flat pp
        on  pc.entity_key    = pp.entity_key
        and pc.provider_type = pp.provider_type
        and pc.canonical_id  = pp.canonical_id
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
    cf.filing_date_current,
    pf.filing_date_prior,
    a.iapd_url,
    c.provider_type,

    n.entity_key is not null                        as is_new_adviser,
    pf.entity_key is null and n.entity_key is null  as has_no_prior_filing,

    coalesce(c.providers_current, [])  as providers_current,
    coalesce(c.providers_prior,   [])  as providers_prior,
    coalesce(c.providers_added,   [])  as providers_added,
    coalesce(c.providers_dropped, [])  as providers_dropped,
    coalesce(af.funds, [])             as adviser_funds,

    case
        when n.entity_key  is not null                 then 'new_adviser'
        when pf.entity_key is null                     then 'no_prior_data'
        when c.added_count > 0 and c.dropped_count > 0 then 'swapped'
        when c.added_count > 0                         then 'added'
        when c.dropped_count > 0                       then 'dropped'
        else                                                'unchanged'
    end as change_type

from changes_agg c
join adviser_info   a  using (entity_key)
join current_filings cf using (entity_key)
left join prior_filings  pf using (entity_key)
left join new_advisers   n  using (entity_key)
left join adviser_funds  af using (entity_key)
order by a.assets_under_management desc nulls last, a.legal_name
