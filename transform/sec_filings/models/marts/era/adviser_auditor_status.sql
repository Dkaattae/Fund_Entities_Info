{{ config(materialized='table') }}

-- Use case 5: one row per ERA adviser with the PCAOB status of the auditors
-- on its LATEST filing. Powers the Auditor Watch dashboard page.
--
-- Lead-gen logic: an adviser whose funds are audited by a non-PCAOB firm
-- either (a) will need a PCAOB-registered + inspected auditor as AUM grows
-- past SEC-registration territory (custody-rule audits), (b) is winding
-- down, (c) stays exempt, or (d) is a fraud signal. same_auditor_same_aum_
-- advisers exposes template-filing clusters — many "advisers" sharing one
-- auditor AND one identical AUM value (the INDICATOR GLOBAL pattern: 98
-- filers all reporting exactly $80M).

with latest as (
    select * from {{ ref('era_latest_filing') }}
),

auditors as (
    select * from {{ ref('stg_era_auditors') }}
    where raw_name is not null
),

adviser_auditors as (
    select
        l.entity_key,
        logical_or(coalesce(a.is_pcaob_registered, false))
            as has_pcaob_registered,
        logical_or(coalesce(a.is_pcaob_registered, false)
                   and coalesce(a.is_pcaob_inspected, false))
            as has_pcaob_inspected,
        logical_or(not coalesce(a.is_pcaob_registered, false))
            as has_non_pcaob,
        count(distinct a.raw_name) as auditor_count,
        string_agg(distinct a.raw_name, '; ' order by a.raw_name)
            as auditor_names,
        string_agg(distinct
            case when not coalesce(a.is_pcaob_registered, false)
                 then a.raw_name end,
            '; ') as non_pcaob_auditor_names,
        string_agg(distinct a.country, '; ' order by a.country)
            as auditor_countries
    from latest l
    join auditors a on a.filing_id = l.filing_id
    group by 1
),

-- Template-filing signal: distinct advisers sharing the same auditor AND the
-- exact same reported AUM. Legitimate books rarely collide to the dollar;
-- scam farms filing from one template do.
pairs as (
    select distinct
        l.entity_key,
        upper(trim(a.raw_name)) as auditor_key,
        l.assets_under_management as aum
    from latest l
    join auditors a on a.filing_id = l.filing_id
    where l.assets_under_management is not null
      and l.assets_under_management > 0
),

clusters as (
    select auditor_key, aum, count(distinct entity_key) as advisers
    from pairs
    group by 1, 2
),

template_signal as (
    select p.entity_key, max(c.advisers) as same_auditor_same_aum_advisers
    from pairs p
    join clusters c using (auditor_key, aum)
    group by 1
)

select
    l.entity_key,
    l.legal_name,
    l.business_name,
    l.main_city,
    l.main_state,
    l.main_country,
    l.assets_under_management,
    case
        when l.assets_under_management is null then 'unknown'
        when l.assets_under_management < 150000000 then '< $150M'
        when l.assets_under_management < 1000000000 then '$150M - $1B'
        else '>= $1B'
    end as aum_bucket,
    case
        when not aa.has_pcaob_registered then 'no_pcaob_auditor'
        when aa.has_non_pcaob then 'mixed'
        when not aa.has_pcaob_inspected then 'registered_not_inspected'
        else 'pcaob_inspected'
    end as auditor_status,
    aa.auditor_count,
    aa.auditor_names,
    aa.non_pcaob_auditor_names,
    aa.auditor_countries,
    coalesce(t.same_auditor_same_aum_advisers, 1) as same_auditor_same_aum_advisers,
    l.date_submitted as latest_filing_date,
    l.fiscal_year,
    l.iapd_url
from latest l
join adviser_auditors aa using (entity_key)
left join template_signal t using (entity_key)
