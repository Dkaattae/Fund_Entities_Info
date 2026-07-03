{{ config(materialized='table') }}

-- One row per (entity_key, reporting_year).
-- reporting_year = annual_amendment_fiscal_year from the annual amendment.
-- Other-amendments are assigned to the reporting year of the most recent prior annual.
-- latest_filing_id is the most recent amendment of any type within that year;
-- it equals annual_filing_id unless an other-amendment was filed after the annual.

with history as (
    select * from {{ ref('era_filing_history') }}
),

annuals as (
    select
        entity_key,
        filing_id               as annual_filing_id,
        date_submitted          as annual_filing_date,
        fiscal_year             as reporting_year,
        assets_under_management as aum
    from history
    where is_annual_amendment_era
      and fiscal_year is not null
),

-- Other-amendments inherit the reporting year of the most recent prior annual
other_amendments as (
    select
        h.entity_key,
        h.filing_id,
        h.date_submitted,
        any_value(h.assets_under_management)           as aum,
        max_by(a.reporting_year, a.annual_filing_date) as reporting_year
    from history h
    join annuals a
        on  a.entity_key         = h.entity_key
        and a.annual_filing_date <= h.date_submitted
    where h.is_other_amendment_era
    group by h.entity_key, h.filing_id, h.date_submitted
),

all_with_year as (
    select entity_key, annual_filing_id as filing_id, annual_filing_date as date_submitted, reporting_year, aum
    from annuals
    union all
    select entity_key, filing_id, date_submitted, reporting_year, aum
    from other_amendments
),

latest_per_year as (
    select
        entity_key,
        reporting_year,
        max_by(filing_id, date_submitted) as latest_filing_id,
        max(date_submitted)               as latest_filing_date,
        -- Most-recent NON-NULL AUM reported anywhere in the year. A blank AUM on a
        -- later amendment means "unchanged", so it must not override an earlier
        -- reported value (max_by ignores rows whose ordering key is null).
        max_by(aum, if(aum is not null, date_submitted, null)) as assets_under_management
    from all_with_year
    group by entity_key, reporting_year
)

select
    l.entity_key,
    l.reporting_year,
    a.annual_filing_id,
    a.annual_filing_date,
    l.latest_filing_id,
    l.latest_filing_date,
    l.assets_under_management,
    l.latest_filing_id != a.annual_filing_id as is_superseded_by_amendment
from latest_per_year l
join annuals a using (entity_key, reporting_year)
-- A few advisers file two annual amendments claiming the same fiscal year
-- (e.g. a re-filed annual the following March). Keep the latest annual — it
-- supersedes the earlier one — so the (entity_key, reporting_year) grain holds.
qualify row_number() over (
    partition by l.entity_key, l.reporting_year
    order by a.annual_filing_date desc, a.annual_filing_id desc
) = 1
order by entity_key, reporting_year
