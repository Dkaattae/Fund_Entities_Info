{{ config(materialized='table') }}

-- Detects two closure signals by comparing consecutive ERA filings per adviser:
--
-- fund_removed: a Form D file_number present in filing N-1 is absent in filing N.
--               The adviser stopped reporting that specific fund in their Form ADV.
--
-- aum_zeroed:   the adviser's total AUM was > 0 in filing N-1 and is 0 in filing N.
--               All assets under management were wound down.
--
-- One row per closure event. filing_date_current is when the closure was first detected.

with history as (
    select * from {{ ref('era_filing_history') }}
),

-- Add previous filing context via window functions for each consecutive pair
ranked as (
    select
        entity_key,
        filing_id,
        date_submitted,
        assets_under_management,
        lag(filing_id) over (
            partition by entity_key
            order by date_submitted asc nulls last, filing_id asc
        ) as prior_filing_id,
        lag(date_submitted) over (
            partition by entity_key
            order by date_submitted asc nulls last, filing_id asc
        ) as prior_date_submitted,
        lag(assets_under_management) over (
            partition by entity_key
            order by date_submitted asc nulls last, filing_id asc
        ) as prior_aum
    from history
),

-- ── Signal: AUM dropped to zero ────────────────────────────────────────────
aum_zeroed as (
    select
        entity_key,
        filing_id                  as filing_id_current,
        date_submitted             as filing_date_current,
        prior_filing_id,
        prior_date_submitted       as filing_date_prior,
        'aum_zeroed'               as closure_signal,
        cast(null as string)       as form_d_file_number,
        assets_under_management    as current_aum,
        prior_aum
    from ranked
    where coalesce(assets_under_management, 0) = 0
      and coalesce(prior_aum, 0) > 0
      and prior_filing_id is not null
),

-- ── Signal: specific fund removed from Form ADV ────────────────────────────
-- All (entity_key, filing_id, form_d_file_number) links across all filings
filing_fund_links as (
    select distinct
        coalesce(b.firm_crd, b.sec_adviser_number) as entity_key,
        b.filing_id,
        fdn.form_d_file_number
    from {{ source('era_adv', 'form_d_num') }} fdn
    join {{ ref('stg_era_base') }} b using (filing_id)
    where coalesce(b.firm_crd, b.sec_adviser_number) is not null
      and fdn.form_d_file_number is not null
),

-- All consecutive filing pairs per entity
filing_pairs as (
    select
        entity_key,
        filing_id              as filing_id_current,
        date_submitted         as filing_date_current,
        prior_filing_id,
        prior_date_submitted   as filing_date_prior
    from ranked
    where prior_filing_id is not null
),

-- Funds that existed in the prior filing
funds_in_prior as (
    select
        fp.entity_key,
        fp.filing_id_current,
        fp.filing_date_current,
        fp.prior_filing_id,
        fp.filing_date_prior,
        fl.form_d_file_number
    from filing_pairs fp
    join filing_fund_links fl
        on  fl.entity_key = fp.entity_key
        and fl.filing_id  = fp.prior_filing_id
),

-- Funds still present in the current filing
funds_in_current as (
    select fp.entity_key, fp.filing_id_current, fl.form_d_file_number
    from filing_pairs fp
    join filing_fund_links fl
        on  fl.entity_key = fp.entity_key
        and fl.filing_id  = fp.filing_id_current
),

-- Funds that disappeared between the two consecutive filings
fund_removed as (
    select
        p.entity_key,
        p.filing_id_current,
        p.filing_date_current,
        p.prior_filing_id,
        p.filing_date_prior,
        'fund_removed'           as closure_signal,
        p.form_d_file_number,
        cast(null as numeric)    as current_aum,
        cast(null as numeric)    as prior_aum
    from funds_in_prior p
    left join funds_in_current c
        on  c.entity_key         = p.entity_key
        and c.filing_id_current  = p.filing_id_current
        and c.form_d_file_number = p.form_d_file_number
    where c.form_d_file_number is null
),

-- ── Combine signals ────────────────────────────────────────────────────────
all_closures as (
    select * from aum_zeroed
    union all
    select * from fund_removed
),

-- Adviser info from latest filing for display + IAPD link
adviser_info as (
    select entity_key, legal_name, business_name, main_city, main_state, iapd_url
    from {{ ref('era_latest_filing') }}
),

-- Fund name from Form D for fund_removed rows
fund_meta as (
    select distinct
        file_num,
        any_value(primary_issuer_name)      as fund_name,
        any_value(edgar_fund_history_url)   as edgar_fund_history_url
    from {{ ref('form_d_pooled_funds') }}
    where file_num is not null
    group by file_num
)

select
    c.entity_key,
    a.legal_name,
    a.business_name,
    a.main_city,
    a.main_state,
    a.iapd_url,

    c.closure_signal,
    c.filing_id_current,
    c.filing_date_current,
    c.prior_filing_id,
    c.filing_date_prior,

    date_trunc(c.filing_date_current, quarter)   as closure_quarter,
    format_date('%Y-Q%Q', c.filing_date_current) as closure_quarter_label,

    c.form_d_file_number,
    fm.fund_name,
    fm.edgar_fund_history_url,

    c.current_aum,
    c.prior_aum

from all_closures c
left join adviser_info a  using (entity_key)
left join fund_meta    fm on fm.file_num = c.form_d_file_number
order by c.filing_date_current desc, c.entity_key
