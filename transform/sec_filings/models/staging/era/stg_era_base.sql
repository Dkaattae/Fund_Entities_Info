with src as (
    select * from {{ source('era_adv', 'base') }}
)

select
    filing_id,
    nullif(form_version, 'None')                                  as form_version,
    safe.parse_date('%m/%d/%Y', nullif(date_submitted, 'None'))   as date_submitted,
    nullif(_1_a, 'None')                                          as legal_name,
    nullif(_1_b1, 'None')                                         as business_name,
    nullif(_1_d, 'None')                                          as sec_adviser_number,
    cast(nullif(_1_e1, -1) as string)                             as firm_crd,
    nullif(_1_f1_street_1, 'None')                                as main_street1,
    nullif(_1_f1_street_2, 'None')                                as main_street2,
    nullif(_1_f1_city, 'None')                                    as main_city,
    nullif(_1_f1_state, 'None')                                   as main_state,
    nullif(_1_f1_country, 'None')                                 as main_country,
    nullif(_1_f1_postal, 'None')                                  as main_postal_code,
    nullif(_1_f3, 'None')                                         as phone_number,
    nullif(_3_a, 'None')                                          as org_form,
    nullif(_3_b, 'None')                                          as fiscal_year_end,
    nullif(_3_c_state, 'None')                                    as state_of_org,
    nullif(_3_c_country, 'None')                                  as country_of_org,
    safe.parse_date('%m/%d/%Y', nullif(execution_date, 'None'))   as execution_date,
    nullif(execution_type, 'None')                                as execution_type,
    nullif(signatory, 'None')                                     as signatory,
    nullif(_2_b_assets, -1)                                       as assets_under_management,
    filing_month
from src
where filing_id is not null
