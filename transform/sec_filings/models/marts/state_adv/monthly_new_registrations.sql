{{ config(materialized='table') }}

-- Monthly time series of new (firm, state) registrations.
-- Counts the same RIA once per state it registers in (per the user spec:
-- "include the same ria register in different state").
--
-- Derived from registration_date in the registrations feed.

with reg as (
    select * from {{ ref('stg_state_registrations') }}
),

reg_first as (
    select
        firm_crd,
        regulator_state,
        registration_type,
        min(registration_date) as registration_date
    from reg
    where registration_date is not null
    group by firm_crd, regulator_state, registration_type
)

select
    date_trunc(registration_date, month) as registration_month,
    registration_type,
    count(*)                             as new_registration_count,
    count(distinct firm_crd)             as new_firms_count,
    count(distinct regulator_state)      as states_touched
from reg_first
group by registration_month, registration_type
order by registration_month, registration_type
