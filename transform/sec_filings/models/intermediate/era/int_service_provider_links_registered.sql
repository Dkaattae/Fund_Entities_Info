{{ config(materialized='view') }}

-- int_service_provider_links with canonical_id routed through the persistent
-- provider_registry. Downstream marts consume THIS model, not the raw links.
--
-- FUND_ADMIN: canonical_id becomes the stable registry provider_id (sp_…) —
-- a normalizer tweak or seed edit re-mints the content-derived key, but the
-- registry keeps the sp_ id, so history and future graph keys survive.
-- Other provider types keep their canonical_id unchanged for now (PCAOB/SEC/
-- LEI keys are already stable real-world IDs; NAME-fingerprint types migrate
-- when their identity work lands — see project_plan Problem 1 item 3).
--
-- coalesce fallback: a brand-new cluster that appears before the registry's
-- next append still gets its content key instead of NULL, and converts to
-- its sp_ id on the next full pipeline run.

select
    l.provider_type,
    l.filing_id,
    l.reference_id,
    l.subreference_id,
    l.raw_name,
    l.normalized_name,
    l.alias_canonical_name,
    l.sec_number,
    l.crd_number,
    l.pcaob_number,
    l.lei,
    l.city,
    l.state,
    l.country,
    l.filing_month,
    case
        when l.provider_type = 'FUND_ADMIN'
            then coalesce(r.provider_id, l.canonical_id)
        else l.canonical_id
    end as canonical_id,
    l.canonical_id as legacy_canonical_id,
    r.provider_id
from {{ ref('int_service_provider_links') }} l
left join {{ ref('provider_registry') }} r
    on l.canonical_id = r.match_key
-- Drop identity-less mentions (no raw_name, no registry number → null
-- canonical_id in raw links; a handful of junk auditor rows). Every mart
-- already filtered these out individually.
where l.canonical_id is not null
