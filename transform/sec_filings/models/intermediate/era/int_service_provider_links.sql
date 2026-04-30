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
)

select
    provider_type,
    filing_id,
    reference_id,
    subreference_id,
    raw_name,
    normalized_name,
    sec_number,
    crd_number,
    pcaob_number,
    lei,
    city,
    state,
    country,
    filing_month,
    case
        when pcaob_number is not null
            then concat('PCAOB:', cast(pcaob_number as string))
        when sec_number is not null and sec_number != ''
            then concat('SEC:', sec_number)
        when lei is not null and lei != ''
            then concat('LEI:', lei)
        when normalized_name is not null and normalized_name != ''
            then concat(
                'NAME:',
                cast(farm_fingerprint(concat(
                    provider_type, '|',
                    normalized_name, '|',
                    coalesce(lower(city), ''), '|',
                    coalesce(lower(country), '')
                )) as string)
            )
        else null
    end as canonical_id
from with_normalized
