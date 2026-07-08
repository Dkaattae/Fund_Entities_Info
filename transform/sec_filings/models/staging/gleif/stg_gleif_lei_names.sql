{{ config(materialized='table') }}

-- All name variants per LEI (legal + other + transliterated) with the two
-- normalization keys used for fund-admin matching, precomputed here once per
-- GLEIF refresh so downstream joins don't re-run regexes over ~4M names.
-- Materialized as a table for the same reason (staging default is view).

select
    lei,
    name,
    name_type,
    name_rank,
    {{ normalize_provider_name('name') }}   as norm_light,
    {{ normalize_fund_admin_name('name') }} as norm_aggressive
from {{ source('gleif', 'lei_names') }}
where name is not null and trim(name) != ''
