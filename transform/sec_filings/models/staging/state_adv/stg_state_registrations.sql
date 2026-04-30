with src as (
    select * from {{ source('state_adviser', 'state_adviser_registrations_raw') }}
)

select
    cast(firm_crd as string)                                  as firm_crd,
    upper(nullif(trim(regulator_state), ''))                  as regulator_state,
    nullif(trim(registration_status), '')                     as registration_status,
    safe.parse_date('%Y-%m-%d', nullif(registration_date, '')) as registration_date,
    upper(nullif(trim(registration_type), ''))                as registration_type,
    safe.parse_date('%Y-%m-%d', nullif(snapshot_date, ''))    as snapshot_date
from src
where firm_crd is not null and firm_crd != ''
  and regulator_state is not null and regulator_state != ''
