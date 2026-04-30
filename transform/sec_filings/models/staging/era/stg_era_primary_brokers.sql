with src as (
    select * from {{ source('era_adv', 'primary_brokers') }}
)

select
    filing_id,
    reference_id,
    nullif(name_of_prime_broker, 'None')                   as raw_name,
    nullif(sec_number, 'None')                             as sec_number,
    cast(nullif(crd_number, -1) as string)                 as crd_number,
    nullif(city, 'None')                                   as city,
    nullif(state, 'None')                                  as state,
    nullif(country, 'None')                                as country,
    nullif(custodian, 'None') = 'Y'                        as is_also_custodian,
    filing_month
from src
where filing_id is not null
