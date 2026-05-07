{{ config(materialized='table') }}

-- "Newly emerging" private funds.
--
-- Filters (all must hold):
--   * Pooled investment fund
--   * Issuer year_of_inc >= our Form D backfill floor (auto-derived as
--     min year of filing_date in stg_form_d_submission). This keeps the
--     "no prior Form D" check trustworthy: an entity that didn't exist
--     before our data window can't have filed Form D before it.
--   * Date of first sale yet to occur
--   * This is the issuer CIK's only Form D in our ingested data
--   * The Form D file_num was NOT reported by any adviser in any earlier
--     Form ADV (ERA) filing
--
-- Each surviving row is then bucketed by relationship to the adviser
-- found via int_form_d_adviser_link:
--   * adviser_also_new   — adviser's earliest ADV filing within ±N days
--   * adviser_established — adviser exists in ADV with older first filing
--   * no_adv_found       — no Form ADV link (may have promoter fallback)

with funds as (
    select * from {{ ref('form_d_pooled_funds') }}
),

-- Related persons for each Form D filing, aggregated into an array
related_persons_agg as (
    select
        accession_number,
        array_agg(
            struct(
                full_name,
                relationship_1,
                relationship_2,
                relationship_3,
                is_promoter
            )
            order by person_seq_key
        ) as related_persons
    from {{ ref('stg_form_d_related_persons') }}
    group by accession_number
),

-- Self-join on related persons: find other pooled funds sharing a named person.
-- Groups by (this fund, other fund) to collect all shared person names in one row.
shared_person_funds_raw as (
    select
        rp1.accession_number,
        f2.primary_issuer_name  as shared_fund_name,
        f2.file_num             as shared_fund_file_num,
        f2.primary_issuer_cik   as shared_fund_cik,
        f2.filing_date          as shared_fund_filing_date,
        array_agg(rp1.full_name order by rp1.full_name) as via_persons
    from {{ ref('stg_form_d_related_persons') }} rp1
    join {{ ref('stg_form_d_related_persons') }} rp2
        on  rp1.full_name        = rp2.full_name
        and rp1.accession_number != rp2.accession_number
    join {{ ref('form_d_pooled_funds') }} f2
        on rp2.accession_number = f2.accession_number
    group by 1, 2, 3, 4, 5
),

shared_person_funds_agg as (
    select
        accession_number,
        count(*)  as shared_fund_count,
        array_agg(
            struct(
                shared_fund_name,
                shared_fund_file_num,
                shared_fund_cik,
                shared_fund_filing_date,
                via_persons
            )
            order by shared_fund_filing_date desc
        ) as funds_with_shared_persons
    from shared_person_funds_raw
    group by accession_number
),

backfill_floor as (
    select extract(year from min(filing_date)) as floor_year
    from {{ ref('stg_form_d_submission') }}
),

issuer_filing_counts as (
    select primary_issuer_cik, count(*) as form_d_count
    from funds
    where primary_issuer_cik is not null
    group by primary_issuer_cik
),

-- Has this file_num been reported in ADV PRIOR to the Form D's filing month?
file_num_prior_adv as (
    select
        f.accession_number,
        max(case
            when parse_date('%Y%m%d', fdn.filing_month || '01') < f.filing_date
            then 1 else 0
        end) = 1 as file_num_in_prior_adv
    from funds f
    left join {{ source('era_adv', 'form_d_num') }} fdn
        on f.file_num = fdn.form_d_file_number
    group by f.accession_number
),

link as (
    select * from {{ ref('int_form_d_adviser_link') }}
),

candidates as (
    select
        f.*,
        ifc.form_d_count,
        fnp.file_num_in_prior_adv,
        bf.floor_year
    from funds f
    cross join backfill_floor bf
    left join issuer_filing_counts ifc using (primary_issuer_cik)
    left join file_num_prior_adv   fnp using (accession_number)
    where
        f.first_sale_yet_to_occur
        and f.year_of_inc is not null
        and f.year_of_inc >= bf.floor_year
        and ifc.form_d_count = 1                              -- only one Form D for this issuer
        and coalesce(fnp.file_num_in_prior_adv, false) = false
)

select
    c.accession_number,
    c.file_num,
    c.filing_date,
    c.primary_issuer_cik,
    c.primary_issuer_name,
    c.year_of_inc,
    c.jurisdiction_of_inc,
    c.edgar_filing_url,
    c.edgar_fund_history_url,
    c.entity_type,
    c.investment_fund_type,
    c.minimum_investment_accepted,
    c.total_offering_amount_numeric,
    c.claims_3c1,
    c.claims_3c7,
    c.claims_506b,
    c.claims_506c,
    c.has_under_100_persons,
    c.has_non_accredited_investors_flag,
    c.low_minimum_investment_flag,
    c.floor_year                                          as form_d_backfill_floor_year,

    l.adviser_source,
    l.adviser_entity_key,
    l.adviser_legal_name,
    l.adviser_business_name,
    l.adviser_first_adv_filing_date,
    l.fallback_promoter_name,

    case
        when l.adviser_source = 'form_adv_join'
             and l.adviser_first_adv_filing_date is not null
             and abs(date_diff(c.filing_date, l.adviser_first_adv_filing_date, day))
                 <= {{ var('emerging_window_days') }}
            then 'adviser_also_new'
        when l.adviser_source = 'form_adv_join'
            then 'adviser_established'
        else 'no_adv_found'
    end as relationship_to_adviser,

    -- Most-recent ADV filing for the linked adviser. Populated only when
    -- there's a real Form ADV link (i.e. relationship is adviser_also_new
    -- or adviser_established); null for no_adv_found rows.
    case when l.adviser_source = 'form_adv_join'
         then l.adviser_latest_adv_filing_id end   as adviser_latest_adv_filing_id,
    case when l.adviser_source = 'form_adv_join'
         then l.adviser_latest_adv_filing_date end as adviser_latest_adv_filing_date,

    -- Related persons on this filing
    coalesce(rpa.related_persons, [])              as related_persons,

    -- Other pooled funds connected via a shared related person
    coalesce(spf.shared_fund_count, 0)             as shared_fund_count,
    spf.funds_with_shared_persons
from candidates c
left join link                  l   using (accession_number)
left join related_persons_agg   rpa using (accession_number)
left join shared_person_funds_agg spf using (accession_number)
order by c.filing_date desc, c.primary_issuer_cik
