{{ config(materialized='table') }}

-- One row per (entity, filing). Joined with filing_types so each row
-- carries amendment flags + fiscal year end.

with base as (
    select * from {{ ref('stg_era_base') }}
),

types as (
    select * from {{ ref('stg_era_filing_types') }}
)

select
    coalesce(b.firm_crd, b.sec_adviser_number) as entity_key,
    b.firm_crd,
    b.sec_adviser_number,
    b.legal_name,
    b.business_name,
    b.filing_id,
    b.filing_month,
    b.date_submitted,
    b.fiscal_year_end,
    b.execution_type,
    b.execution_date,
    b.assets_under_management,
    coalesce(t.is_initial_sec_registration,    false) as is_initial_sec_registration,
    coalesce(t.is_annual_amendment_registered, false) as is_annual_amendment_registered,
    coalesce(t.is_other_amendment_registered,  false) as is_other_amendment_registered,
    coalesce(t.is_initial_state_registration,  false) as is_initial_state_registration,
    coalesce(t.is_initial_sec_era,             false) as is_initial_sec_era,
    coalesce(t.is_annual_amendment_era,        false) as is_annual_amendment_era,
    coalesce(t.is_other_amendment_era,         false) as is_other_amendment_era,
    coalesce(t.is_initial_state_era,           false) as is_initial_state_era,
    coalesce(t.is_final_state_era,             false) as is_final_state_era,
    coalesce(t.is_final_sec_era,               false) as is_final_sec_era,
    t.annual_amendment_fiscal_year,
    -- Convenience: any amendment flag = true
    coalesce(
        t.is_annual_amendment_registered
        or t.is_other_amendment_registered
        or t.is_annual_amendment_era
        or t.is_other_amendment_era,
        false
    ) as is_amendment,
    row_number() over (
        partition by coalesce(b.firm_crd, b.sec_adviser_number)
        order by b.date_submitted, b.filing_id
    ) as filing_seq
from base b
left join types t using (filing_id)
where coalesce(b.firm_crd, b.sec_adviser_number) is not null
order by entity_key, filing_seq
