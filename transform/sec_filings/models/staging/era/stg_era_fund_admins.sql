with src as (
    select * from {{ source('era_adv', 'fund_admins') }}
)

select
    filing_id,
    reference_id,
    nullif(name_of_administrator, 'None')                  as raw_name,
    nullif(city, 'None')                                   as city,
    nullif(state, 'None')                                  as state,
    nullif(country, 'None')                                as country,
    nullif(related_person, 'None') = 'Y'                   as is_related_person,
    nullif(statements, 'None')                             as statements,
    nullif(who_sends_statements, 'None')                   as who_sends_statements,
    filing_month
from src
where filing_id is not null
