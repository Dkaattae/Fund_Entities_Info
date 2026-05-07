{{ config(materialized='table') }}

-- Adviser lifecycle transitions detected from ERA (Form ADV) filing history.
-- One row per transition event per adviser.
--
-- transition_type values (detectable with current ERA data):
--   new_era          – first-ever SEC ERA filing
--   era_to_ria       – adviser had ERA filings, then filed initial SEC registration (upgrade)
--   new_ria          – initial SEC registration with no prior ERA history in our data
--   era_withdrawal   – adviser filed a final SEC ERA report (exiting)
--   new_state_era    – first-ever state ERA filing
--   new_state_ria    – first-ever state RIA registration
--
-- Note: RIA → ERA downgrades are not detectable without full Form ADV (RIA) data.

with history as (
    select * from {{ ref('era_filing_history') }}
),

-- Advisers that have at least one ERA annual/other amendment (established ERA filers)
established_era as (
    select distinct entity_key
    from history
    where is_annual_amendment_era or is_other_amendment_era
),

-- Classify every initial / final filing event
events as (
    select
        h.entity_key,
        h.filing_id,
        h.date_submitted,
        h.legal_name,
        h.business_name,
        h.assets_under_management,
        date_trunc(h.date_submitted, quarter)    as event_quarter,
        format_date('%Y-Q%Q', h.date_submitted)  as event_quarter_label,

        case
            when h.is_initial_sec_registration and e.entity_key is not null then 'era_to_ria'
            when h.is_initial_sec_registration and e.entity_key is null     then 'new_ria'
            when h.is_initial_sec_era                                        then 'new_era'
            when h.is_final_sec_era                                          then 'era_withdrawal'
            when h.is_initial_state_era                                      then 'new_state_era'
            when h.is_initial_state_registration                             then 'new_state_ria'
        end as transition_type

    from history h
    left join established_era e using (entity_key)
    where h.is_initial_sec_registration
       or h.is_initial_sec_era
       or h.is_final_sec_era
       or h.is_initial_state_era
       or h.is_initial_state_registration
),

-- Adviser IAPD link
adviser_urls as (
    select entity_key, iapd_url
    from {{ ref('era_latest_filing') }}
)

select
    e.entity_key,
    e.legal_name,
    e.business_name,
    e.assets_under_management,
    e.filing_id,
    e.date_submitted,
    e.event_quarter,
    e.event_quarter_label,
    e.transition_type,
    u.iapd_url
from events e
left join adviser_urls u using (entity_key)
where e.transition_type is not null
order by e.date_submitted desc, e.entity_key
