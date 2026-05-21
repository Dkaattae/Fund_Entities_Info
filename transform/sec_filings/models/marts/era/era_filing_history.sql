{{ config(materialized='table') }}

-- One row per (entity, filing). Joined with filing_types so each row
-- carries amendment flags + fiscal year end.

with base as (
    select * from {{ ref('stg_era_base') }}
),

types as (
    select * from {{ ref('stg_era_filing_types') }}
),

month_map as (
    select * from unnest([
        struct('JANUARY'   as month_name, 1  as month_num),
        struct('FEBRUARY'  as month_name, 2  as month_num),
        struct('MARCH'     as month_name, 3  as month_num),
        struct('APRIL'     as month_name, 4  as month_num),
        struct('MAY'       as month_name, 5  as month_num),
        struct('JUNE'      as month_name, 6  as month_num),
        struct('JULY'      as month_name, 7  as month_num),
        struct('AUGUST'    as month_name, 8  as month_num),
        struct('SEPTEMBER' as month_name, 9  as month_num),
        struct('OCTOBER'   as month_name, 10 as month_num),
        struct('NOVEMBER'  as month_name, 11 as month_num),
        struct('DECEMBER'  as month_name, 12 as month_num)
    ])
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
    -- Fiscal year: priority 1 = declared annual_amendment_fiscal_year when present,
    -- priority 2 = derived from FYE month vs submission month,
    -- priority 3 = fallback to submission year.
    case
        when t.annual_amendment_fiscal_year is not null
            then t.annual_amendment_fiscal_year
        when b.fiscal_year_end is not null
             and b.date_submitted is not null
             and mm.month_num is not null
            then case
                when extract(month from b.date_submitted) > mm.month_num
                    then extract(year from b.date_submitted)
                else extract(year from b.date_submitted) - 1
            end
        else extract(year from b.date_submitted)
    end as fiscal_year,
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
left join month_map mm on upper(b.fiscal_year_end) = mm.month_name
where coalesce(b.firm_crd, b.sec_adviser_number) is not null
order by entity_key, filing_seq
