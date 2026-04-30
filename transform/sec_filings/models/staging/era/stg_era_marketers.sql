with src as (
    select * from {{ source('era_adv', 'marketers') }}
)

select
    filing_id,
    reference_id,
    subreference_id,
    nullif(name_of_marketer, 'None')                       as raw_name,
    nullif(sec_number, 'None')                             as sec_number,
    cast(nullif(crd_number, -1) as string)                 as crd_number,
    nullif(related_person, 'None') = 'Y'                   as is_related_person,
    nullif(city, 'None')                                   as city,
    nullif(state, 'None')                                  as state,
    nullif(country, 'None')                                as country,
    nullif(websites, 'None')                               as websites,
    filing_month
from src
where filing_id is not null
