{{ config(materialized='table') }}

-- Broker-dealer master: one row per CIK, derived by replaying the monthly
-- raw snapshots in order (dbt port of the retired pandas merge in
-- ingestion/broker-dealer/merge_files.py — same semantics, verified
-- column-identical against the pandas-built table at migration, 2026-07-10).
--
-- Status reflects the LATEST raw month:
--   New          first ever appearance is the latest month
--   Reregistered absent the month before, present again (start_month reset;
--                original withdrawn_month kept)
--   Active       present in both of the last two months
--   Withdrawn    absent in the latest month (status persists month over month)
-- start_month     start of the latest presence streak; NULL for firms present
--                 since the very first raw month (pandas initial-load rows
--                 carried '' — preserved as NULL, don't "fix" it: a value
--                 here means a firm actually appeared/reappeared mid-history)
-- withdrawn_month the month of the most recent present→absent transition
-- last_observed_month  the latest raw month (same for every row — table as-of)
-- Entity columns come from the last month the CIK was present.

with snapshots as (
    select * from {{ ref('stg_broker_dealer_snapshots') }}
),

bounds as (
    select
        max(month_idx) as latest_idx,
        max(file_month) as latest_month
    from snapshots
),

-- Presence timeline per CIK: flag streak starts (first month, or a return
-- after >=1 absent month) and withdrawals (the month AFTER a presence row
-- with a gap or nothing following it).
timeline as (
    select
        cik,
        file_month,
        month_idx,
        lag(month_idx)  over (partition by cik order by month_idx) as prev_present_idx,
        lead(month_idx) over (partition by cik order by month_idx) as next_present_idx
    from snapshots
),

per_cik as (
    select
        t.cik,
        min(t.month_idx) as first_seen_idx,
        max(t.month_idx) as last_seen_idx,
        -- Latest streak start: no previous presence row, or a gap before this one.
        max(case
                when t.prev_present_idx is null or t.prev_present_idx < t.month_idx - 1
                then t.month_idx
            end) as last_streak_start_idx,
        -- Latest withdrawal: the month right after a presence row that is
        -- followed by a gap (or by nothing, if before the latest raw month).
        max(case
                when (t.next_present_idx is null and t.month_idx < b.latest_idx)
                  or t.next_present_idx > t.month_idx + 1
                then t.month_idx + 1
            end) as last_withdrawal_idx
    from timeline t
    cross join bounds b
    group by t.cik
),

month_names as (
    select distinct month_idx, file_month from snapshots
),

-- Entity attributes from the last month the CIK was present.
latest_attrs as (
    select cik, name, film_number, address, address2, city, state, zip
    from snapshots
    qualify row_number() over (partition by cik order by month_idx desc) = 1
)

select
    a.cik,
    a.name,
    a.film_number,
    a.address,
    a.address2,
    a.city,
    a.state,
    a.zip,
    case
        when p.last_seen_idx = b.latest_idx then
            case
                when p.first_seen_idx = b.latest_idx        then 'New'
                when p.last_streak_start_idx = b.latest_idx then 'Reregistered'
                else 'Active'
            end
        else 'Withdrawn'
    end as status,
    -- NULL for the initial-load cohort (streak began at the first raw month).
    case
        when p.last_streak_start_idx > 1 then ms.file_month
    end as start_month,
    mw.file_month as withdrawn_month,
    b.latest_month as last_observed_month
from per_cik p
cross join bounds b
join latest_attrs a using (cik)
left join month_names ms on ms.month_idx = p.last_streak_start_idx
left join month_names mw on mw.month_idx = p.last_withdrawal_idx
