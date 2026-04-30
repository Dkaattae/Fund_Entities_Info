{{ config(materialized='table') }}

-- For each ERA, indicate whether the firm also appears in the state-RIA feed.
-- The Form ADV filing_types table records whether a state-registration request
-- was submitted alongside the filing; the state-adviser feed records whether
-- the firm is currently visible as a state RIA. We surface both so they can
-- be reconciled.

with era_latest as (
    select * from {{ ref('era_latest_filing') }}
),

filing_state_flags as (
    -- Roll up filing_types across ALL of an ERA's filings: did they ever
    -- request state registration / file as a state ERA?
    select
        coalesce(b.firm_crd, b.sec_adviser_number) as entity_key,
        max(case when ft.is_initial_state_registration then 1 else 0 end) = 1
            as ever_filed_state_registration_request,
        max(case when ft.is_initial_state_era then 1 else 0 end) = 1
            as ever_filed_initial_state_era,
        max(case when ft.is_final_state_era then 1 else 0 end) = 1
            as ever_filed_final_state_era
    from {{ ref('stg_era_base') }} b
    left join {{ ref('stg_era_filing_types') }} ft using (filing_id)
    where coalesce(b.firm_crd, b.sec_adviser_number) is not null
    group by entity_key
),

state_master as (
    select * from {{ ref('stg_state_master') }}
),

state_regs as (
    select
        firm_crd,
        array_agg(distinct regulator_state ignore nulls order by regulator_state) as state_jurisdictions,
        count(distinct case when registration_type = 'STATE' then regulator_state end) as state_registration_count,
        count(distinct case when registration_type = 'ERA'   then regulator_state end) as state_era_registration_count
    from {{ ref('stg_state_registrations') }}
    group by firm_crd
)

select
    e.entity_key,
    e.firm_crd,
    e.sec_adviser_number,
    e.legal_name,
    e.business_name,
    -- From state-adviser feed
    sm.firm_crd is not null                                     as in_state_adviser_feed,
    sm.status                                                   as state_master_status,
    sm.first_seen_date                                          as state_first_seen_date,
    sm.last_observed_date                                       as state_last_observed_date,
    coalesce(sr.state_registration_count, 0)                    as state_registration_count,
    coalesce(sr.state_era_registration_count, 0)                as state_era_registration_count,
    sr.state_jurisdictions,
    -- From this ERA's own Form ADV filing-type history
    coalesce(fsf.ever_filed_state_registration_request, false)  as ever_filed_state_registration_request,
    coalesce(fsf.ever_filed_initial_state_era, false)           as ever_filed_initial_state_era,
    coalesce(fsf.ever_filed_final_state_era, false)             as ever_filed_final_state_era,
    -- Convenience reconciliation flag
    case
        when sm.firm_crd is not null then true
        when coalesce(fsf.ever_filed_state_registration_request, false)
          or coalesce(fsf.ever_filed_initial_state_era, false) then true
        else false
    end as is_also_state_registered
from era_latest e
left join state_master       sm  on e.firm_crd = sm.firm_crd
left join state_regs         sr  on e.firm_crd = sr.firm_crd
left join filing_state_flags fsf on e.entity_key = fsf.entity_key
