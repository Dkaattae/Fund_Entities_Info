{{ config(materialized='view') }}

-- Long-format union of every service-provider mention across all ERA filings.
-- Each row preserves the (filing_id, reference_id) link back to the ERA, plus
-- a canonical_id that identifies the same provider across rows whose
-- raw names disagree. Canonical-id priority:
--   1. PCAOB number (auditors)
--   2. SEC number  (brokers, marketers, custodians)
--   3. LEI         (custodians)
--   4. FUND_ADMIN: NAME:<first 12 hex of MD5(normalized canonical name)>
--      Seeds/fund_admin_aliases maps known raw_name → canonical_name.
--      Unknown admins fall back to normalizing their own raw_name.
--      City and country are excluded — same firm across offices stays one ID.
--   5. NAME:<farm_fingerprint(type|normalized_name|city|country)>  (all other types)

with auditors as (
    select
        'AUDITOR' as provider_type,
        filing_id,
        reference_id,
        cast(null as int64) as subreference_id,
        raw_name,
        cast(null as string) as sec_number,
        cast(null as string) as crd_number,
        pcaob_number,
        cast(null as string) as lei,
        city, state, country,
        filing_month
    from {{ ref('stg_era_auditors') }}
),

fund_admins as (
    select
        'FUND_ADMIN' as provider_type,
        filing_id,
        reference_id,
        cast(null as int64) as subreference_id,
        raw_name,
        cast(null as string) as sec_number,
        cast(null as string) as crd_number,
        cast(null as int64)  as pcaob_number,
        cast(null as string) as lei,
        city, state, country,
        filing_month
    from {{ ref('stg_era_fund_admins') }}
),

primary_brokers as (
    select
        'PRIME_BROKER' as provider_type,
        filing_id,
        reference_id,
        cast(null as int64) as subreference_id,
        raw_name,
        sec_number,
        crd_number,
        cast(null as int64) as pcaob_number,
        cast(null as string) as lei,
        city, state, country,
        filing_month
    from {{ ref('stg_era_primary_brokers') }}
),

marketers as (
    select
        'MARKETER' as provider_type,
        filing_id,
        reference_id,
        subreference_id,
        raw_name,
        sec_number,
        crd_number,
        cast(null as int64) as pcaob_number,
        cast(null as string) as lei,
        city, state, country,
        filing_month
    from {{ ref('stg_era_marketers') }}
),

custodians as (
    select
        'CUSTODIAN' as provider_type,
        filing_id,
        reference_id,
        cast(null as int64) as subreference_id,
        raw_name,
        sec_number,
        cast(null as string) as crd_number,
        cast(null as int64)  as pcaob_number,
        lei,
        city, state, country,
        filing_month
    from {{ ref('stg_era_custodians') }}
),

unioned as (
    select * from auditors
    union all select * from fund_admins
    union all select * from primary_brokers
    union all select * from marketers
    union all select * from custodians
),

-- Alias seed: known raw_name → canonical_name for FUND_ADMIN (no registry IDs exist).
-- Run scripts/discover_unknown_fund_admins.py to append new unknowns as placeholders.
fund_admin_aliases as (
    select
        lower(trim(raw_name))  as raw_name_key,
        canonical_name
    from {{ ref('fund_admin_aliases') }}
),

with_normalized as (
    select
        u.*,
        {{ normalize_provider_name('u.raw_name') }} as normalized_name,
        fa.canonical_name                            as alias_canonical_name,
        -- FUND_ADMIN: normalize the seed canonical_name if matched, else normalize raw_name.
        -- All other types: use normalized raw_name (city/country stay in their own columns).
        case
            when u.provider_type = 'FUND_ADMIN'
                then {{ normalize_provider_name('coalesce(fa.canonical_name, u.raw_name)') }}
            else {{ normalize_provider_name('u.raw_name') }}
        end as effective_normalized_name
    from unioned u
    left join fund_admin_aliases fa
        on  u.provider_type = 'FUND_ADMIN'
        and lower(trim(u.raw_name)) = fa.raw_name_key
),

-- Per (normalized_name, provider_type): find the most authoritative registry id
-- across ALL filings. Priority: PCAOB > SEC > LEI.
-- This resolves the common case where the same provider is sometimes reported
-- without a registry number (yielding a NAME:hash) and sometimes with one.
best_canonical as (
    select
        normalized_name,
        provider_type,
        coalesce(
            min(case when pcaob_number is not null
                     then concat('PCAOB:', cast(pcaob_number as string)) end),
            min(case when sec_number is not null and sec_number != ''
                     then concat('SEC:', sec_number) end),
            min(case when lei is not null and lei != ''
                     then concat('LEI:', lei) end)
        ) as authoritative_id
    from with_normalized
    where normalized_name is not null and normalized_name != ''
    group by normalized_name, provider_type
),

with_raw_canonical as (
    select
        w.*,
        case
            when w.pcaob_number is not null
                then concat('PCAOB:', cast(w.pcaob_number as string))
            when w.sec_number is not null and w.sec_number != ''
                then concat('SEC:', w.sec_number)
            when w.lei is not null and w.lei != ''
                then concat('LEI:', w.lei)
            -- FUND_ADMIN: name-only hash (city/country excluded so same firm across offices
            -- stays one ID). First 12 hex chars of MD5 keep IDs short and readable.
            -- Seed alias wins; unknown firms fall back to their own normalized name.
            when w.provider_type = 'FUND_ADMIN'
                and w.effective_normalized_name is not null
                and w.effective_normalized_name != ''
                then concat('NAME:', substr(to_hex(md5(w.effective_normalized_name)), 1, 12))
            -- All other types: include city + country in the fingerprint to disambiguate
            -- providers with identical names in different markets.
            when w.normalized_name is not null and w.normalized_name != ''
                then concat(
                    'NAME:',
                    cast(farm_fingerprint(concat(
                        w.provider_type, '|',
                        w.normalized_name, '|',
                        coalesce(lower(w.city), ''), '|',
                        coalesce(lower(w.country), '')
                    )) as string)
                )
            else null
        end as raw_canonical_id
    from with_normalized w
)

select
    w.provider_type,
    w.filing_id,
    w.reference_id,
    w.subreference_id,
    w.raw_name,
    w.normalized_name,
    w.alias_canonical_name,
    w.sec_number,
    w.crd_number,
    w.pcaob_number,
    w.lei,
    w.city,
    w.state,
    w.country,
    w.filing_month,
    -- Upgrade NAME: ids to the authoritative registry id where known.
    -- Skipped for FUND_ADMIN — no registry IDs exist, upgrade would never fire anyway.
    case
        when w.provider_type != 'FUND_ADMIN'
            and w.raw_canonical_id like 'NAME:%'
            and bc.authoritative_id is not null
            then bc.authoritative_id
        else w.raw_canonical_id
    end as canonical_id
from with_raw_canonical w
left join best_canonical bc
    on  w.normalized_name = bc.normalized_name
    and w.provider_type   = bc.provider_type
