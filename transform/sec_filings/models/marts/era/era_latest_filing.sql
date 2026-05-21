{{ config(materialized='table') }}

-- One row per ERA entity (CRD where available, else SEC adviser number).
-- Picks the most recent filing by date_submitted, then filing_id as tiebreaker.
-- Joins back to stg_era_base for address and org fields not carried in filing_history.

with latest as (
    select *,
        row_number() over (
            partition by entity_key
            order by date_submitted desc nulls last, filing_id desc
        ) as rn
    from {{ ref('era_filing_history') }}
),

base as (
    select * from {{ ref('stg_era_base') }}
)

select
    l.entity_key,
    l.firm_crd,
    l.sec_adviser_number,
    l.legal_name,
    l.business_name,
    b.main_street1,
    b.main_street2,
    b.main_city,
    b.main_state,
    b.main_country,
    b.main_postal_code,
    b.org_form,
    b.state_of_org,
    b.country_of_org,
    l.fiscal_year_end,
    l.execution_type,
    l.execution_date,
    b.signatory,
    l.assets_under_management,
    l.date_submitted,
    l.filing_id,
    l.filing_month,
    l.is_annual_amendment_era,
    l.is_other_amendment_era,
    l.is_initial_sec_era,
    l.fiscal_year,
    case when l.firm_crd is not null
        then concat('https://www.adviserinfo.sec.gov/Firm/', l.firm_crd)
    end as iapd_url
from latest l
join base b using (filing_id)
where l.rn = 1
