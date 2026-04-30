with src as (
    select * from {{ source('era_adv', 'auditors') }}
)

select
    filing_id,
    reference_id,
    nullif(name_of_auditing_firm, 'None')                  as raw_name,
    nullif(city, 'None')                                   as city,
    nullif(state, 'None')                                  as state,
    nullif(country, 'None')                                as country,
    nullif(independent, 'None') = 'Y'                      as is_independent,
    nullif(pcaob_registered, 'None') = 'Y'                 as is_pcaob_registered,
    nullif(pcaob_number, -1)                               as pcaob_number,
    nullif(pcaob_inspected, 'None') = 'Y'                  as is_pcaob_inspected,
    filing_month
from src
where filing_id is not null
