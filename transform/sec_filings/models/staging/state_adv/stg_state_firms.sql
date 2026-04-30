with src as (
    select * from {{ source('state_adviser', 'state_adviser_firms_raw') }}
)

select
    cast(firm_crd as string)                                as firm_crd,
    nullif(trim(business_name), '')                         as business_name,
    nullif(trim(legal_name), '')                            as legal_name,
    nullif(trim(umbrella_registration), '')                 as umbrella_registration,
    nullif(trim(main_street1), '')                          as main_street1,
    nullif(trim(main_street2), '')                          as main_street2,
    nullif(trim(main_city), '')                             as main_city,
    nullif(trim(main_state), '')                            as main_state,
    nullif(trim(main_country), '')                          as main_country,
    nullif(trim(main_postal_code), '')                      as main_postal_code,
    nullif(trim(main_phone), '')                            as main_phone,
    safe.parse_date('%Y-%m-%d', nullif(filing_date, ''))    as filing_date,
    nullif(trim(form_version), '')                          as form_version,
    nullif(trim(org_form), '')                              as org_form,
    nullif(trim(state_of_org), '')                          as state_of_org,
    nullif(trim(country_of_org), '')                        as country_of_org,
    safe_cast(nullif(total_employees, '') as int64)         as total_employees,
    safe_cast(nullif(aum_discretionary, '') as numeric)     as aum_discretionary,
    safe_cast(nullif(aum_non_discretionary, '') as numeric) as aum_non_discretionary,
    safe_cast(nullif(aum_total, '') as numeric)             as aum_total,
    safe_cast(nullif(account_count, '') as int64)           as account_count,
    nullif(trim(websites), '')                              as websites,
    safe.parse_date('%Y-%m-%d', nullif(snapshot_date, ''))  as snapshot_date
from src
where firm_crd is not null and firm_crd != ''
