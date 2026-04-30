{{ config(materialized='table') }}

-- Per-firm state-RIA monthly history. One row per (firm_crd, history_month)
-- representing the firm's state at the LAST snapshot observed in that month,
-- plus month-over-month deltas.
--
-- Grain choice: daily snapshots produce ~22× the row count without adding
-- much signal — most days have zero events. Monthly is the natural cadence
-- for tracking adviser footprint changes (matches the SEC ERA monthly bulk).
-- Will be sparse until each month fills out.

with firms as (
    select * from {{ ref('stg_state_firms') }}
),

regs as (
    select * from {{ ref('stg_state_registrations') }}
),

regs_per_snapshot as (
    select
        firm_crd,
        snapshot_date,
        array_agg(distinct regulator_state ignore nulls order by regulator_state) as jurisdictions,
        count(distinct case when registration_type = 'STATE' then regulator_state end) as state_registration_count,
        count(distinct case when registration_type = 'ERA'   then regulator_state end) as state_era_registration_count,
        count(distinct regulator_state) as total_jurisdiction_count
    from regs
    group by firm_crd, snapshot_date
),

per_snapshot as (
    select
        f.firm_crd,
        f.snapshot_date,
        date_trunc(f.snapshot_date, month) as history_month,
        f.business_name,
        f.legal_name,
        f.main_state,
        f.main_city,
        f.main_country,
        f.aum_total,
        f.aum_discretionary,
        f.aum_non_discretionary,
        f.total_employees,
        f.account_count,
        coalesce(r.jurisdictions, [])               as jurisdictions,
        coalesce(r.state_registration_count, 0)     as state_registration_count,
        coalesce(r.state_era_registration_count, 0) as state_era_registration_count,
        coalesce(r.total_jurisdiction_count, 0)     as total_jurisdiction_count
    from firms f
    left join regs_per_snapshot r using (firm_crd, snapshot_date)
),

-- Pick the LATEST snapshot within each (firm, month) as the month's record
monthly as (
    select * except (rn)
    from (
        select
            *,
            row_number() over (
                partition by firm_crd, history_month
                order by snapshot_date desc
            ) as rn
        from per_snapshot
    )
    where rn = 1
),

-- Window over each firm's monthly history to compute deltas
windowed as (
    select
        *,
        lag(history_month)            over w as prev_history_month,
        lag(snapshot_date)            over w as prev_month_snapshot_date,
        lag(jurisdictions)            over w as prev_jurisdictions,
        lag(total_jurisdiction_count) over w as prev_total_jurisdiction_count,
        lag(aum_total)                over w as prev_aum_total,
        first_value(history_month)    over w as first_history_month,
        first_value(snapshot_date)    over w as first_seen_date,
        last_value(snapshot_date)     over (
            partition by firm_crd
            order by history_month
            rows between unbounded preceding and unbounded following
        )                                    as last_observed_date,
        row_number()                  over w as month_seq
    from monthly
    window w as (partition by firm_crd order by history_month)
),

with_deltas as (
    select
        * except (prev_jurisdictions),
        array(
            select x from unnest(jurisdictions) x
            where x not in unnest(coalesce(prev_jurisdictions, []))
        ) as jurisdictions_added,
        array(
            select x from unnest(coalesce(prev_jurisdictions, [])) x
            where x not in unnest(jurisdictions)
        ) as jurisdictions_dropped,
        total_jurisdiction_count - coalesce(prev_total_jurisdiction_count, 0) as jurisdiction_count_change,
        aum_total - prev_aum_total                                            as aum_change
    from windowed
)

select
    firm_crd,
    history_month,
    snapshot_date                  as month_end_snapshot_date,
    month_seq,
    business_name,
    legal_name,
    main_state,
    main_city,
    main_country,
    aum_total,
    aum_discretionary,
    aum_non_discretionary,
    total_employees,
    account_count,
    jurisdictions,
    total_jurisdiction_count,
    state_registration_count,
    state_era_registration_count,
    -- Lifecycle pointers
    first_history_month,
    first_seen_date,
    last_observed_date,
    prev_history_month,
    prev_month_snapshot_date,
    -- Month-over-month deltas
    jurisdictions_added,
    jurisdictions_dropped,
    jurisdiction_count_change,
    aum_change,
    -- Derived event flags
    month_seq = 1                                                  as is_first_month,
    array_length(jurisdictions_added)  > 0                         as added_state_this_month,
    array_length(jurisdictions_dropped) > 0                        as dropped_state_this_month
from with_deltas
order by firm_crd, history_month
