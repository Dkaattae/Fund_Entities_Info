{{ config(tags=['gleif']) }}

-- One row per LEI with the slim attribute set the matching layer needs.
-- Countries are ISO-2 (join through seed country_iso_map to compare with
-- ERA filing country names).

select
    lei,
    legal_name,
    legal_city,
    legal_region,
    legal_country,
    hq_city,
    hq_region,
    hq_country,
    legal_jurisdiction,
    entity_category,
    legal_form_code,
    entity_status,
    registration_status,
    initial_registration_date,
    last_update_date
from {{ source('gleif', 'lei_records') }}
