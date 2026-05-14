-- Backward-compatible interface over stg_state_latest.
-- Consumed by era_state_registration_status and any other model that expects
-- the old master-table column contract (status, first_seen_date, withdrawn_date,
-- last_observed_date). No longer reads from the Python-maintained BQ master table.
select
    firm_crd,
    business_name,
    legal_name,
    main_state,
    main_city,
    main_country,
    state_of_org,
    aum_total,
    aum_discretionary,
    aum_non_discretionary,
    total_employees,
    status,
    first_seen_date,
    withdrawn_date,
    last_observed_date
from {{ ref('stg_state_latest') }}
