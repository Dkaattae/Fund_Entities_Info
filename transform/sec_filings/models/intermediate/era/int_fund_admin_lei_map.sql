{{ config(materialized='table', tags=['gleif']) }}

-- One row per fund-admin canonical_id: the best GLEIF LEI candidate for that
-- admin, or NULLs when nothing matched. This is a MAPPING table — it does NOT
-- rewire canonical_id (that lands with the stable provider registry, see
-- project_plan "Sequencing"). Consumers can require match_tier = 1 for
-- high-confidence use and treat tier 2 as a review queue.
--
-- Match tiers:
--   1  exact light-normalized name match (normalize_provider_name both sides)
--   2  aggressive-normalized match (normalize_fund_admin_name) — only kept
--      when the LEI's legal/HQ country corroborates the filing country,
--      because aggressive keys ("apex") collide across the global LEI pool.
-- Candidate ranking inside a tier prefers specific (multi-token) name keys
-- over single generic tokens ("apex", "carta" collide badly across 3.4M
-- global entities), then corroborated country, ACTIVE entities, ISSUED
-- registrations, GENERAL entity category, and legal-name matches over
-- previous/trading-name matches.
--
-- match_confidence: 'high' = tier 1, multi-token key AND country match —
-- safe to consume programmatically. 'medium' = tier 1 with one of the two,
-- or corroborated multi-token tier 2. 'low' = the rest — review only.

with links as (
    select *
    from {{ ref('int_service_provider_links') }}
    where provider_type = 'FUND_ADMIN'
      and canonical_id is not null
),

admins as (
    select
        canonical_id,
        min(coalesce(alias_canonical_name, raw_name)) as admin_name,
        count(distinct filing_id) as filings
    from links
    group by canonical_id
),

-- Most frequent filing country per admin (evidence, not identity).
admin_country as (
    select canonical_id, country as admin_country
    from links
    where country is not null
    group by canonical_id, country
    qualify row_number() over (
        partition by canonical_id order by count(*) desc, country
    ) = 1
),

admin_geo as (
    select
        ac.canonical_id,
        ac.admin_country,
        iso.iso2 as admin_iso2
    from admin_country ac
    left join {{ ref('country_iso_map') }} iso
        on ac.admin_country = iso.country_name
),

-- Every distinct name string observed for an admin (raw filing variants plus
-- the seed canonical name) — more matching surface than the display name alone.
variants as (
    select distinct canonical_id, raw_name as variant_name from links
    union distinct
    select distinct canonical_id, alias_canonical_name
    from links where alias_canonical_name is not null
),

variant_norms as (
    select
        canonical_id,
        variant_name,
        {{ normalize_provider_name('variant_name') }}   as norm_light,
        {{ normalize_fund_admin_name('variant_name') }} as norm_aggressive
    from variants
),

-- GLEIF matching surface: exclude FUND entities (a fund admin is a company,
-- and fund names collide heavily with admin names) and invalid registrations.
lei_names as (
    select
        n.lei,
        n.name       as matched_name,
        n.name_type  as matched_name_type,
        n.name_rank,
        n.norm_light,
        n.norm_aggressive,
        r.legal_name          as lei_legal_name,
        r.legal_city          as lei_legal_city,
        r.legal_country       as lei_legal_country,
        r.hq_country          as lei_hq_country,
        r.entity_category     as lei_entity_category,
        r.entity_status       as lei_entity_status,
        r.registration_status as lei_registration_status
    from {{ ref('stg_gleif_lei_names') }} n
    join {{ ref('stg_gleif_lei_records') }} r using (lei)
    where coalesce(r.entity_category, 'GENERAL') != 'FUND'
      and coalesce(r.registration_status, '') not in ('ANNULLED', 'DUPLICATE')
),

tier1 as (
    select v.canonical_id, n.*, 1 as match_tier, v.norm_light as matched_key
    from variant_norms v
    join lei_names n on v.norm_light = n.norm_light
    where v.norm_light != ''
),

tier2 as (
    select v.canonical_id, n.*, 2 as match_tier, v.norm_aggressive as matched_key
    from variant_norms v
    join admin_geo g on v.canonical_id = g.canonical_id
    join lei_names n
        on  v.norm_aggressive = n.norm_aggressive
        and (n.lei_legal_country = g.admin_iso2 or n.lei_hq_country = g.admin_iso2)
    where length(v.norm_aggressive) >= 4
      and g.admin_iso2 is not null
),

candidates as (
    select * from tier1
    union all
    select * from tier2
),

best_match as (
    select
        c.*,
        coalesce(
            c.lei_legal_country = g.admin_iso2 or c.lei_hq_country = g.admin_iso2,
            false
        ) as country_corroborated,
        array_length(split(c.matched_key, ' ')) >= 2 as multi_token_key
    from candidates c
    left join admin_geo g on c.canonical_id = g.canonical_id
    qualify row_number() over (
        partition by c.canonical_id
        order by
            c.match_tier,
            -- More tokens = more specific key. "apex fund services" must beat
            -- "apex group" even when the latter's country corroborates —
            -- generic short keys pick up unrelated same-country entities.
            array_length(split(c.matched_key, ' ')) desc,
            coalesce(c.lei_legal_country = g.admin_iso2
                     or c.lei_hq_country = g.admin_iso2, false) desc,
            case when c.lei_entity_status = 'ACTIVE' then 0 else 1 end,
            case c.lei_registration_status when 'ISSUED' then 0
                                           when 'LAPSED' then 1
                                           else 2 end,
            case when c.lei_entity_category = 'GENERAL' then 0 else 1 end,
            c.name_rank,
            c.lei
    ) = 1
)

select
    a.canonical_id,
    a.admin_name,
    a.filings,
    g.admin_country,
    g.admin_iso2,
    b.lei,
    b.lei_legal_name,
    b.matched_name,
    b.matched_name_type,
    b.matched_key,
    b.match_tier,
    case
        when b.match_tier = 1 and b.multi_token_key and b.country_corroborated
            then 'high'
        when b.match_tier = 1 and (b.multi_token_key or b.country_corroborated)
            then 'medium'
        when b.match_tier = 2 and b.multi_token_key
            then 'medium'
        when b.match_tier is not null
            then 'low'
    end as match_confidence,
    b.country_corroborated,
    b.lei_legal_city,
    b.lei_legal_country,
    b.lei_hq_country,
    b.lei_entity_category,
    b.lei_entity_status,
    b.lei_registration_status
from admins a
left join admin_geo  g on a.canonical_id = g.canonical_id
left join best_match b on a.canonical_id = b.canonical_id
