{{ config(materialized='table') }}

-- One row per RIA, capturing the very first time the firm appeared
-- anywhere in the state-adviser system. A firm registered in multiple
-- states still has a single first-seen event here.

with master as (
    select * from {{ ref('stg_state_master') }}
),

latest_firm as (
    select
        firm_crd,
        business_name,
        legal_name,
        main_state,
        main_city,
        main_country,
        state_of_org,
        aum_total,
        aum_discretionary,
        aum_non_discretionary,
        total_employees,
        snapshot_date as latest_snapshot_date,
        row_number() over (partition by firm_crd order by snapshot_date desc) as rn
    from {{ ref('stg_state_firms') }}
),

firm_latest as (
    select * except (rn) from latest_firm where rn = 1
)

select
    m.firm_crd,
    coalesce(f.business_name, m.business_name)         as business_name,
    coalesce(f.legal_name, m.legal_name)               as legal_name,
    coalesce(f.main_state, m.main_state)               as main_state,
    coalesce(f.main_city, m.main_city)                 as main_city,
    coalesce(f.main_country, m.main_country)           as main_country,
    coalesce(f.state_of_org, m.state_of_org)           as state_of_org,
    coalesce(f.aum_total, m.aum_total)                 as aum_total,
    coalesce(f.aum_discretionary, m.aum_discretionary) as aum_discretionary,
    coalesce(f.aum_non_discretionary, m.aum_non_discretionary) as aum_non_discretionary,
    coalesce(f.total_employees, m.total_employees)     as total_employees,
    m.status,
    m.first_seen_date,
    m.withdrawn_date,
    m.last_observed_date
from master m
left join firm_latest f using (firm_crd)
order by m.first_seen_date desc, m.firm_crd
