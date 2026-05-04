{{ config(materialized='view') }}

-- Long-format union of every service-provider mention across all ERA filings.
-- Each row preserves the (filing_id, reference_id) link back to the ERA, plus
-- a canonical_id that identifies the same provider across rows whose
-- raw names disagree. Canonical-id priority:
--   1. PCAOB number (auditors)
--   2. SEC number  (brokers, marketers, custodians)
--   3. LEI         (custodians)
--   4. fingerprint of normalized_name + city + country  (fund admins, others)

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

with_normalized as (
    select
        u.*,
        {{ normalize_provider_name('raw_name') }} as normalized_name
    from unioned u
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
    w.sec_number,
    w.crd_number,
    w.pcaob_number,
    w.lei,
    w.city,
    w.state,
    w.country,
    w.filing_month,
    -- Upgrade NAME: ids to the authoritative registry id where known
    case
        when w.raw_canonical_id like 'NAME:%' and bc.authoritative_id is not null
            then bc.authoritative_id
        else w.raw_canonical_id
    end as canonical_id
from with_raw_canonical w
left join best_canonical bc
    on  w.normalized_name = bc.normalized_name
    and w.provider_type   = bc.provider_type
