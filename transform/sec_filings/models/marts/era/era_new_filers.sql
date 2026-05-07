{{ config(materialized='table') }}

-- All initial IARD filers from the filing_types table, left-joined to base.
-- filing_types covers ALL IARD submissions (ERA + full RIA + State).
-- base covers ERA advisers only, so RIA filers have name/CRD = null.
--
-- adviser_type classification (priority order):
--   SEC RIA   – initial_sec_registration_request = Y  (converting ERA or new RIA)
--   SEC ERA   – initial_sec_era_report = Y
--   State RIA – initial_state_registration_request = Y
--   State ERA – initial_state_era_report = Y

with types as (
    select * from {{ source('era_adv', 'filing_types') }}
    where
        nullif(initial_sec_registration_request,    'None') = 'Y'
        or nullif(initial_sec_era_report,           'None') = 'Y'
        or nullif(initial_state_registration_request,'None') = 'Y'
        or nullif(initial_state_era_report,         'None') = 'Y'
),

base as (
    select * from {{ ref('stg_era_base') }}
)

select
    t.filing_id,
    t.filing_month,

    -- Type flags
    nullif(t.initial_sec_registration_request,     'None') = 'Y' as is_initial_sec_registration,
    nullif(t.initial_sec_era_report,               'None') = 'Y' as is_initial_sec_era,
    nullif(t.initial_state_registration_request,   'None') = 'Y' as is_initial_state_registration,
    nullif(t.initial_state_era_report,             'None') = 'Y' as is_initial_state_era,

    -- Adviser type (first matching rule wins)
    case
        when nullif(t.initial_sec_registration_request,   'None') = 'Y' then 'SEC RIA'
        when nullif(t.initial_sec_era_report,             'None') = 'Y' then 'SEC ERA'
        when nullif(t.initial_state_registration_request, 'None') = 'Y' then 'State RIA'
        when nullif(t.initial_state_era_report,           'None') = 'Y' then 'State ERA'
    end as adviser_type,

    -- ERA-specific fields (null for RIA/State-only filers)
    coalesce(b.firm_crd, b.sec_adviser_number) as entity_key,
    b.firm_crd,
    b.sec_adviser_number,
    b.legal_name,
    b.business_name,
    b.date_submitted,
    b.assets_under_management,
    b.main_city,
    b.main_state,
    case when b.firm_crd is not null
        then concat('https://www.adviserinfo.sec.gov/Firm/', b.firm_crd)
    end as iapd_url

from types t
left join base b using (filing_id)
