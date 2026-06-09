{{ config(materialized='table') }}

-- Closure signals for ERA advisers. Three signals:
--
-- final_filing: the adviser filed an SEC/state "final filing" (final_sec_era_report
--               or final_state_era_report). This is the authoritative, highest-confidence
--               closure marker — the adviser is withdrawing from ERA reporting.
--
-- fund_removed: a Form D file_number present in year Y-1's snapshot is absent in year Y's
--               snapshot. Both years come from int_era_annual_snapshot, which reconstructs
--               each year's fund list from the latest filing that actually reported funds —
--               so a sparse amendment that omitted the fund schedule no longer fabricates a
--               removal.
--
-- aum_zeroed:   adviser AUM was > 0 in the year Y-1 snapshot and is GENUINELY reported as 0
--               in year Y. A blank/unreported AUM in year Y is treated as unknown (not a
--               closure): amendments routinely leave AUM blank when unchanged, so null != 0.
--
-- Year-over-year comparison is strictly Y vs Y-1, so skipped years surface as missing rows
-- rather than inflated gaps. is_late_filer flags cases where the gap between the two
-- snapshots' latest filing dates exceeds 18 months.

with snapshot as (
    select * from {{ ref('int_era_annual_snapshot') }}
),

-- Consecutive year pairs: year Y joined to year Y-1 for the same entity.
year_pairs as (
    select
        curr.entity_key,
        curr.reporting_year                                              as current_year,
        curr.latest_filing_id                                            as filing_id_current,
        curr.latest_filing_date                                          as filing_date_current,
        curr.is_superseded_by_amendment                                  as current_is_amended,
        prev.reporting_year                                              as prior_year,
        prev.latest_filing_id                                            as prior_filing_id,
        prev.latest_filing_date                                          as filing_date_prior,
        date_diff(curr.latest_filing_date, prev.latest_filing_date, day) as days_since_prior_filing,
        curr.assets_under_management                                     as current_aum,
        prev.assets_under_management                                     as prior_aum,
        curr.fund_file_numbers                                           as current_funds,
        prev.fund_file_numbers                                           as prior_funds
    from snapshot curr
    join snapshot prev
        on  prev.entity_key     = curr.entity_key
        and prev.reporting_year = curr.reporting_year - 1
),

-- ── Signal: final filing ───────────────────────────────────────────────────
-- Authoritative closure marker. lag() over the full filing history gives the
-- filing immediately preceding the final one. Dedupe to the most recent final
-- filing per entity.
filing_history as (
    select
        entity_key,
        filing_id,
        date_submitted,
        assets_under_management,
        is_final_sec_era,
        is_final_state_era,
        lag(filing_id)      over w as prior_filing_id,
        lag(date_submitted) over w as filing_date_prior
    from {{ ref('era_filing_history') }}
    window w as (partition by entity_key order by date_submitted, filing_id)
),

final_filing as (
    select
        entity_key,
        filing_id                                              as filing_id_current,
        date_submitted                                         as filing_date_current,
        prior_filing_id,
        filing_date_prior,
        date_diff(date_submitted, filing_date_prior, day)      as days_since_prior_filing,
        'final_filing'                                         as closure_signal,
        cast(null as string)                                   as form_d_file_number,
        assets_under_management                                as current_aum,
        cast(null as numeric)                                  as prior_aum
    from filing_history
    where is_final_sec_era or is_final_state_era
    qualify row_number() over (
        partition by entity_key order by date_submitted desc, filing_id desc
    ) = 1
),

-- ── Signal: AUM dropped to zero ────────────────────────────────────────────
-- Fires only on a genuine reported 0 this year (current_aum is not null), never on a
-- blank/unreported AUM, which means "unchanged" rather than "zeroed".
aum_zeroed as (
    select
        entity_key,
        filing_id_current,
        filing_date_current,
        prior_filing_id,
        filing_date_prior,
        days_since_prior_filing,
        'aum_zeroed'          as closure_signal,
        cast(null as string)  as form_d_file_number,
        current_aum,
        prior_aum
    from year_pairs
    where current_aum = 0
      and coalesce(prior_aum, 0) > 0
),

-- ── Signal: fund removed ───────────────────────────────────────────────────
-- Unnest prior year's fund list and keep only funds absent from current year.
-- Handles current_funds = NULL (adviser reported zero funds this year).
fund_removed as (
    select
        yp.entity_key,
        yp.filing_id_current,
        yp.filing_date_current,
        yp.prior_filing_id,
        yp.filing_date_prior,
        yp.days_since_prior_filing,
        'fund_removed'        as closure_signal,
        fn                    as form_d_file_number,
        yp.current_aum,
        yp.prior_aum
    from year_pairs yp
    cross join unnest(yp.prior_funds) as fn
    where (
        yp.current_funds is null
        or not exists (
            select 1 from unnest(yp.current_funds) as cf where cf = fn
        )
    )
),

-- ── Combine ────────────────────────────────────────────────────────────────
all_closures as (
    select * from final_filing
    union all
    select * from aum_zeroed
    union all
    select * from fund_removed
),

adviser_info as (
    select entity_key, legal_name, business_name, main_city, main_state, iapd_url
    from {{ ref('era_latest_filing') }}
),

fund_meta as (
    select distinct
        file_num,
        any_value(primary_issuer_name)    as fund_name,
        any_value(edgar_fund_history_url) as edgar_fund_history_url
    from {{ ref('int_form_d_filings') }}
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
    c.days_since_prior_filing,
    -- True when the gap between consecutive annual snapshots exceeds 18 months.
    -- These advisers likely missed a filing year; their closure may have occurred
    -- earlier than filing_date_current suggests.
    c.days_since_prior_filing > 548 as is_late_filer,

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
