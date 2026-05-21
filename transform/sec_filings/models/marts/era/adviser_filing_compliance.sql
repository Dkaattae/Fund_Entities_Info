{{ config(materialized='table') }}

-- Advisers who are past their annual amendment due date but have no filing
-- for the current reporting year.
--
-- Due date = 90 days after fiscal year end. fiscal_year_end is a month name
-- (e.g. DECEMBER, MARCH) sourced from Form ADV Item 3.B.
-- The current reporting year is derived dynamically from the data.

with base as (
    select * from {{ ref('stg_era_base') }}
),

filing_history as (
    select * from {{ ref('era_filing_history') }}
),

-- Current reporting year: most recent fiscal year with annual amendments.
current_year as (
    select max(fiscal_year) as yr
    from {{ ref('era_filing_history') }}
    where is_annual_amendment_era
),

-- Map month name to month number
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
),

-- Latest filing per adviser with their fiscal year end
latest_filing as (
    select
        coalesce(b.firm_crd, b.sec_adviser_number) as entity_key,
        max_by(b.filing_id, b.date_submitted)       as last_filing_id,
        max(b.date_submitted)                       as last_filing_date,
        any_value(b.fiscal_year_end)                as fiscal_year_end,
        any_value(b.legal_name)                     as legal_name,
        any_value(b.business_name)                  as business_name,
        any_value(b.assets_under_management)        as assets_under_management,
        any_value(b.main_city)                      as main_city,
        any_value(b.main_state)                     as main_state
    from base b
    where coalesce(b.firm_crd, b.sec_adviser_number) is not null
    group by entity_key
),

-- Advisers who have already filed for the current reporting year
filed_current_year as (
    select distinct entity_key
    from filing_history h
    cross join current_year c
    where (h.is_annual_amendment_era or h.is_other_amendment_era)
      and h.fiscal_year = c.yr
),

-- Compute due date per adviser and flag overdue ones
overdue as (
    select
        lf.entity_key,
        lf.last_filing_id,
        lf.last_filing_date,
        lf.fiscal_year_end,
        lf.legal_name,
        lf.business_name,
        lf.assets_under_management,
        lf.main_city,
        lf.main_state,
        c.yr as current_reporting_year,
        coalesce(mm.month_num, 12) as fye_month_num,
        -- Due date: last day of FYE month in the current reporting year + 90 days
        date_add(
            last_day(date(c.yr, coalesce(mm.month_num, 12), 1)),
            interval 90 day
        ) as due_date
    from latest_filing lf
    cross join current_year c
    left join month_map mm on upper(lf.fiscal_year_end) = mm.month_name
    left join filed_current_year f using (entity_key)
    where f.entity_key is null   -- not yet filed for current year
),

final as (
    select
        entity_key,
        legal_name,
        business_name,
        assets_under_management,
        fiscal_year_end,
        main_city,
        main_state,
        current_reporting_year,
        due_date,
        last_filing_date,
        date_diff(current_date(), due_date, day) as days_overdue
    from overdue
    where current_date() > due_date   -- only flag once due date has passed
)

select * from final
order by days_overdue desc, assets_under_management desc nulls last
