{{ config(materialized='table') }}

-- One row per ERA entity (CRD where available, else SEC adviser number).
-- Picks the most recent filing by date_submitted.

with base as (
    select * from {{ ref('stg_era_base') }}
),

keyed as (
    select
        coalesce(firm_crd, sec_adviser_number) as entity_key,
        firm_crd,
        sec_adviser_number,
        legal_name,
        business_name,
        main_street1, main_street2, main_city, main_state,
        main_country, main_postal_code,
        org_form, fiscal_year_end, state_of_org, country_of_org,
        execution_type, execution_date, signatory,
        assets_under_management,
        date_submitted,
        filing_id,
        filing_month,
        row_number() over (
            partition by coalesce(firm_crd, sec_adviser_number)
            order by date_submitted desc nulls last, filing_id desc
        ) as rn
    from base
    where coalesce(firm_crd, sec_adviser_number) is not null
)

select * except (rn) from keyed where rn = 1
