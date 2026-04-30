with src as (
    select * from {{ source('state_adviser', 'state_adviser_master') }}
)

select
    cast(firm_crd as string)                                   as firm_crd,
    nullif(trim(business_name), '')                            as business_name,
    nullif(trim(legal_name), '')                               as legal_name,
    nullif(trim(main_state), '')                               as main_state,
    nullif(trim(main_city), '')                                as main_city,
    nullif(trim(main_country), '')                             as main_country,
    nullif(trim(state_of_org), '')                             as state_of_org,
    safe_cast(nullif(aum_total, '') as numeric)                as aum_total,
    safe_cast(nullif(aum_discretionary, '') as numeric)        as aum_discretionary,
    safe_cast(nullif(aum_non_discretionary, '') as numeric)    as aum_non_discretionary,
    safe_cast(nullif(total_employees, '') as int64)            as total_employees,
    nullif(trim(status), '')                                   as status,
    safe.parse_date('%Y-%m-%d', nullif(first_seen_date, ''))   as first_seen_date,
    safe.parse_date('%Y-%m-%d', nullif(withdrawn_date, ''))    as withdrawn_date,
    safe.parse_date('%Y-%m-%d', nullif(last_observed_date, '')) as last_observed_date
from src
where firm_crd is not null and firm_crd != ''
