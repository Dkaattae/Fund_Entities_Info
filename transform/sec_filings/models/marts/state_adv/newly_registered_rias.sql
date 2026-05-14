{{ config(materialized='table') }}

-- One row per state RIA: latest firm data joined with their earliest
-- state registration date. Replaces the old dual-source pattern
-- (stg_state_master + stg_state_firms) with a single source: stg_state_latest.

with latest as (
    select * from {{ ref('stg_state_latest') }}
),

-- Earliest STATE registration date per firm — the true "first registered" date,
-- independent of when we started ingesting the daily feed.
first_registration as (
    select
        cast(firm_crd as string)                                         as firm_crd,
        min(safe.parse_date('%Y-%m-%d', registration_date))             as first_registration_date
    from {{ source('state_adviser', 'state_adviser_registrations_raw') }}
    where registration_type = 'STATE'
      and registration_date is not null
      and registration_date != ''
    group by firm_crd
)

select
    l.firm_crd,
    coalesce(l.business_name, l.legal_name) as business_name,
    l.legal_name,
    l.main_street1,
    l.main_street2,
    l.main_city,
    l.main_state,
    l.main_postal_code,
    l.main_country,
    l.main_phone,
    l.websites,
    l.state_of_org,
    l.aum_total,
    l.aum_discretionary,
    l.aum_non_discretionary,
    l.total_employees,
    l.status,
    r.first_registration_date,
    l.first_seen_date,
    l.withdrawn_date,
    l.last_observed_date
from latest l
left join first_registration r using (firm_crd)
order by r.first_registration_date desc, l.firm_crd
