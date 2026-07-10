{{ config(materialized='table') }}

-- Use case 7: late / missing audit reports. One row per audited private fund
-- on its adviser's LATEST filing. Form ADV carries no audit-delivery date,
-- but Schedule D 7.B.1 Q23 gives the state: fs_distributed (23h) and the
-- opinion field, whose 'Report Not Yet Received' value is an explicit
-- "audit outstanding" flag. Advisers must promptly amend 7.B.23 when the
-- audited statements go out, so a latest filing still showing an
-- outstanding/undistributed report past the custody-rule-style deadline
-- (FYE + 120 days; + 180 for fund of funds) is exactly "missing audit
-- report and no amendment in time". The deadline is a benchmark: ERAs are
-- not literally subject to the custody rule's audit provision.
--
-- Advisers who wound down via a final report are excluded (same rule as
-- adviser_filing_compliance); their exits belong to era_fund_closures.

with latest as (
    select * from {{ ref('era_latest_filing') }}
),

funds as (
    select * from {{ ref('stg_era_funds') }}
    where is_audited
),

filing_history as (
    select * from {{ ref('era_filing_history') }}
),

terminated as (
    select fr.entity_key
    from (
        select entity_key, max(date_submitted) as final_date
        from filing_history
        where is_final_sec_era or is_final_state_era
        group by entity_key
    ) fr
    join (
        select entity_key, max(date_submitted) as last_date
        from filing_history
        group by entity_key
    ) la using (entity_key)
    where la.last_date <= fr.final_date
),

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

auditors as (
    select
        filing_id,
        string_agg(distinct raw_name, '; ' order by raw_name) as auditor_names,
        logical_or(not coalesce(is_pcaob_registered, false))  as has_non_pcaob_auditor
    from {{ ref('stg_era_auditors') }}
    where raw_name is not null
    group by filing_id
),

enriched as (
    select
        l.entity_key,
        l.legal_name,
        l.business_name,
        l.assets_under_management,
        l.fiscal_year_end,
        l.iapd_url,
        l.date_submitted as last_filing_date,
        f.fund_id,
        f.fund_name,
        f.fund_type,
        f.gross_asset_value,
        f.is_fund_of_funds,
        f.is_gaap,
        f.fs_distributed,
        f.audit_opinion,
        a.auditor_names,
        coalesce(a.has_non_pcaob_auditor, false) as has_non_pcaob_auditor,
        case
            when f.audit_opinion = 'Report Not Yet Received' then 'report_not_received'
            when f.audit_opinion = 'No'                      then 'qualified_opinion'
            when not coalesce(f.fs_distributed, true)        then 'not_distributed'
            else 'clean'
        end as audit_status,
        -- Adviser-FYE month-end in the filing year (month defaults to December).
        last_day(date(
            extract(year from l.date_submitted), coalesce(mm.month_num, 12), 1
        )) as fye_candidate
    from latest l
    join funds f using (filing_id)
    left join month_map mm on upper(l.fiscal_year_end) = mm.month_name
    left join terminated t on l.entity_key = t.entity_key
    left join auditors a on a.filing_id = l.filing_id
    where t.entity_key is null
),

with_fye as (
    select
        *,
        -- The fiscal year the filing reports on: the most recent FYE
        -- month-end on or before the filing date.
        if(fye_candidate <= last_filing_date,
           fye_candidate,
           last_day(date(extract(year from fye_candidate) - 1,
                         extract(month from fye_candidate), 1))
        ) as reporting_fye_date
    from enriched
),

with_deadline as (
    select
        * except (fye_candidate),
        date_add(reporting_fye_date,
                 interval if(is_fund_of_funds, 180, 120) day) as distribution_deadline
    from with_fye
)

select
    *,
    audit_status in ('report_not_received', 'not_distributed')
        and current_date() > distribution_deadline as is_overdue,
    if(audit_status in ('report_not_received', 'not_distributed')
           and current_date() > distribution_deadline,
       date_diff(current_date(), distribution_deadline, day),
       null) as days_overdue
from with_deadline
