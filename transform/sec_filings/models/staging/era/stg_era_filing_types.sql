with src as (
    select * from {{ source('era_adv', 'filing_types') }}
)

select
    filing_id,
    nullif(initial_sec_registration_request, 'None')              = 'Y' as is_initial_sec_registration,
    nullif(annual_updating_amendment_for_registered_adviser, 'None') = 'Y' as is_annual_amendment_registered,
    nullif(other_than_anual_amendment_for_registered_adviser, 'None') = 'Y' as is_other_amendment_registered,
    nullif(initial_state_registration_request, 'None')            = 'Y' as is_initial_state_registration,
    nullif(initial_sec_era_report, 'None')                        = 'Y' as is_initial_sec_era,
    nullif(annual_updating_amendment_era_report, 'None')          = 'Y' as is_annual_amendment_era,
    nullif(other_than_annual_amendment_era_report, 'None')        = 'Y' as is_other_amendment_era,
    nullif(initial_state_era_report, 'None')                      = 'Y' as is_initial_state_era,
    nullif(final_state_era_report, 'None')                        = 'Y' as is_final_state_era,
    nullif(final_sec_era_report, 'None')                          = 'Y' as is_final_sec_era,
    nullif(annual_updating_amendment_fiscal_year, -1)             as annual_amendment_fiscal_year,
    filing_month
from src
where filing_id is not null
