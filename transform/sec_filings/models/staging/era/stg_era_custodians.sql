with src as (
    select * from {{ source('era_adv', 'custodians') }}
)

select
    filing_id,
    reference_id,
    nullif(legal_name_of_custodian, 'None')                as raw_name,
    nullif(primary_business_name, 'None')                  as business_name,
    nullif(sec_number, 'None')                             as sec_number,
    nullif(legal_entity_identifier, 'None')                as lei,
    nullif(city, 'None')                                   as city,
    nullif(state, 'None')                                  as state,
    nullif(country, 'None')                                as country,
    nullif(related_person, 'None') = 'Y'                   as is_related_person,
    filing_month
from src
where filing_id is not null
