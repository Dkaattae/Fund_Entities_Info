-- Monthly SEC broker-dealer list snapshots, one row per (cik, file_month).
-- file_month is 'yy_mm' (zero-padded, so it also sorts lexicographically);
-- month_idx numbers the months actually present in the raw table, in order —
-- the master derivation replays transitions over these indexes, so a month
-- with no file at all (never downloaded) does not count as a withdrawal.

with months as (
    select
        file_month,
        dense_rank() over (order by file_month) as month_idx
    from (select distinct file_month from {{ source('broker_dealer', 'broker_dealer_raw') }})
)

select
    r.cik,
    r.name,
    r.film_number,
    r.address,
    r.address2,
    r.city,
    r.state,
    r.zip,
    r.file_month,
    m.month_idx,
    last_day(safe.parse_date('%y_%m', r.file_month)) as snapshot_month_end
from {{ source('broker_dealer', 'broker_dealer_raw') }} r
join months m using (file_month)
where r.cik is not null
