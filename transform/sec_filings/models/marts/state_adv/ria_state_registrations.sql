{{ config(materialized='table') }}

-- Per (firm, state) registration row. Includes:
--   * registration_date and status for that state
--   * firm-level AUM (state-level AUM is not reported in the feed)
--   * firm-level totals: how many distinct states the firm is registered in

with reg as (
    select * from {{ ref('stg_state_registrations') }}
),

-- Earliest registration per (firm, state) across all snapshots
reg_first as (
    select
        firm_crd,
        regulator_state,
        registration_type,
        min(registration_date) as registration_date,
        any_value(registration_status) as registration_status
    from reg
    where registration_date is not null
    group by firm_crd, regulator_state, registration_type
),

latest_firm as (
    select
        firm_crd,
        business_name,
        legal_name,
        main_state                              as firm_main_state,
        main_city                               as firm_main_city,
        main_country                            as firm_main_country,
        state_of_org,
        aum_total,
        aum_discretionary,
        aum_non_discretionary,
        total_employees,
        snapshot_date                           as latest_snapshot_date,
        row_number() over (partition by firm_crd order by snapshot_date desc) as rn
    from {{ ref('stg_state_firms') }}
),

firm_latest as (
    select * except (rn) from latest_firm where rn = 1
),

firm_state_counts as (
    select
        firm_crd,
        count(distinct case when registration_type = 'STATE' then regulator_state end) as state_registration_count,
        count(distinct case when registration_type = 'ERA'   then regulator_state end) as era_registration_count,
        count(distinct regulator_state) as total_jurisdiction_count,
        array_agg(distinct regulator_state ignore nulls order by regulator_state) as registered_jurisdictions
    from reg_first
    group by firm_crd
)

select
    r.firm_crd,
    f.business_name,
    f.legal_name,
    r.regulator_state,
    r.registration_type,
    r.registration_status,
    r.registration_date,
    f.firm_main_state,
    f.firm_main_city,
    f.firm_main_country,
    f.state_of_org,
    f.aum_total,
    f.aum_discretionary,
    f.aum_non_discretionary,
    f.total_employees,
    c.state_registration_count,
    c.era_registration_count,
    c.total_jurisdiction_count,
    c.registered_jurisdictions
from reg_first r
left join firm_latest f       using (firm_crd)
left join firm_state_counts c using (firm_crd)
order by r.firm_crd, r.regulator_state
