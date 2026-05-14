-- Latest snapshot per firm, enriched with lifecycle fields derived
-- from the full raw history — no dependency on the Python-maintained master table.
--
--   status:             'Active'    = firm present in the most recent feed snapshot
--                       'Withdrawn' = firm dropped out of the feed
--   first_seen_date:    earliest snapshot_date we observed this firm in the feed
--   last_observed_date: most recent snapshot_date we observed this firm
--   withdrawn_date:     set to last_observed_date when status = 'Withdrawn', else null

with all_snapshots as (
    select * from {{ ref('stg_state_firms') }}
),

latest_snapshot_date as (
    select max(snapshot_date) as max_date from all_snapshots
),

firm_bounds as (
    select
        firm_crd,
        min(snapshot_date) as first_seen_date,
        max(snapshot_date) as last_observed_date
    from all_snapshots
    group by firm_crd
),

latest_per_firm as (
    select * except (rn)
    from (
        select
            *,
            row_number() over (partition by firm_crd order by snapshot_date desc) as rn
        from all_snapshots
    )
    where rn = 1
)

select
    l.*,
    fb.first_seen_date,
    fb.last_observed_date,
    case
        when fb.last_observed_date = m.max_date then 'Active'
        else 'Withdrawn'
    end as status,
    case
        when fb.last_observed_date < m.max_date then fb.last_observed_date
    end as withdrawn_date
from latest_per_firm    l
join firm_bounds        fb using (firm_crd)
cross join latest_snapshot_date m
