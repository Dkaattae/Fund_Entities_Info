{{ config(materialized='table') }}

-- Per Form D filing (pooled investment funds): adviser identification plus
-- the adviser's other Form D file numbers (= other funds they manage).
-- filing_date is exposed so downstream consumers can window to "newly filed".

with funds as (
    select * from {{ ref('form_d_pooled_funds') }}
),

link as (
    select * from {{ ref('int_form_d_adviser_link') }}
),

-- All Form D file numbers an ERA adviser has reported, collapsed per
-- adviser_entity_key, used to surface "the adviser's other funds".
adviser_other_funds as (
    select
        coalesce(b.firm_crd, b.sec_adviser_number) as adviser_entity_key,
        array_agg(distinct fdn.form_d_file_number ignore nulls
                  order by fdn.form_d_file_number) as adviser_form_d_file_numbers
    from {{ source('era_adv', 'form_d_num') }} fdn
    join {{ ref('stg_era_base') }} b using (filing_id)
    where coalesce(b.firm_crd, b.sec_adviser_number) is not null
    group by adviser_entity_key
)

select
    f.accession_number,
    f.file_num,
    f.filing_date,
    f.submission_type,
    f.is_amendment_submission,

    f.primary_issuer_cik,
    f.primary_issuer_name,
    f.year_of_inc,
    f.investment_fund_type,
    f.first_sale_yet_to_occur,
    f.total_amount_sold,
    f.claims_3c1,
    f.claims_3c7,
    f.claims_506b,
    f.claims_506c,

    l.adviser_source,
    l.adviser_entity_key,
    l.adviser_crd,
    l.adviser_sec_number,
    l.adviser_legal_name,
    l.adviser_business_name,
    l.fallback_promoter_name,
    l.adviser_first_adv_filing_date,

    -- Adviser's other Form D file numbers (excluding this one)
    array(
        select x
        from unnest(coalesce(aof.adviser_form_d_file_numbers, [])) as x
        where x != f.file_num
    ) as adviser_other_form_d_file_numbers,
    case when aof.adviser_form_d_file_numbers is null then 0
         else array_length(aof.adviser_form_d_file_numbers) - 1
    end as adviser_other_fund_count
from funds f
left join link              l   using (accession_number)
left join adviser_other_funds aof on l.adviser_entity_key = aof.adviser_entity_key
