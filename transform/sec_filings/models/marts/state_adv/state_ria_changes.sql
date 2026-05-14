{{ config(materialized='table') }}

-- Day-over-day change events for state RIA firms.
-- One row per (firm_crd, snapshot_date) where at least one notable field changed.
-- Events detected:
--   is_first_appearance  – firm seen for the first time in the feed
--   aum_changed          – total AUM differs from the prior snapshot
--   name_changed         – business_name differs from the prior snapshot
--   hq_state_changed     – main_state differs from the prior snapshot
--
-- Only rows with at least one change are emitted — no change, no row.
-- Use this table to answer: "what firms changed AUM / appeared / moved between
-- snapshot A and snapshot B?"

with history as (
    select * from {{ ref('stg_state_firms') }}
),

with_prev as (
    select
        firm_crd,
        snapshot_date,
        business_name,
        main_state,
        main_city,
        aum_total,
        aum_discretionary,
        aum_non_discretionary,
        total_employees,
        account_count,
        lag(snapshot_date)   over w as prev_snapshot_date,
        lag(aum_total)       over w as prev_aum_total,
        lag(business_name)   over w as prev_business_name,
        lag(main_state)      over w as prev_main_state
    from history
    window w as (partition by firm_crd order by snapshot_date)
),

changes as (
    select
        *,
        prev_snapshot_date is null                                                      as is_first_appearance,
        coalesce(aum_total, -1) != coalesce(prev_aum_total, -1)                        as aum_changed,
        coalesce(business_name, '') != coalesce(prev_business_name, '')                as name_changed,
        coalesce(main_state, '') != coalesce(prev_main_state, '')                       as hq_state_changed,
        aum_total - prev_aum_total                                                     as aum_delta
    from with_prev
)

select
    firm_crd,
    snapshot_date,
    prev_snapshot_date,
    business_name,
    prev_business_name,
    main_state,
    prev_main_state,
    main_city,
    aum_total,
    prev_aum_total,
    aum_delta,
    aum_discretionary,
    total_employees,
    account_count,
    is_first_appearance,
    aum_changed,
    name_changed,
    hq_state_changed
from changes
where is_first_appearance
   or aum_changed
   or name_changed
   or hq_state_changed
order by snapshot_date desc, firm_crd
