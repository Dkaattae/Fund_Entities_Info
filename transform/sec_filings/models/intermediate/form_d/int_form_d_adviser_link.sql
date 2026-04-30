{{ config(materialized='view') }}

-- For each Form D filing, attempt to link an investment adviser:
--   1. Primary  : Form D file_num  ↔  era_adv form_d_num.form_d_file_number
--   2. Fallback : Form D related_persons where relationship = 'Promoter'
--
-- Output one row per Form D accession_number with adviser fields and a
-- discriminator (adviser_source).

with filings as (
    select accession_number, file_num, filing_date
    from {{ ref('int_form_d_filings') }}
),

-- ---- Primary linkage via Form ADV (ERA) -----------------------------------
era_link as (
    select distinct
        f.accession_number,
        coalesce(b.firm_crd, b.sec_adviser_number) as adviser_entity_key,
        b.firm_crd                                  as adviser_crd,
        b.sec_adviser_number                        as adviser_sec_number,
        b.legal_name                                as adviser_legal_name,
        b.business_name                             as adviser_business_name
    from filings f
    join {{ source('era_adv', 'form_d_num') }} fdn
      on f.file_num = fdn.form_d_file_number
    join {{ ref('stg_era_base') }} b
      on b.filing_id = fdn.filing_id
),

-- Pick latest known adviser entity per Form D (file_num can repeat across
-- multiple ERA filings — collapse to one)
era_link_dedup as (
    select
        accession_number,
        any_value(adviser_entity_key)    as adviser_entity_key,
        any_value(adviser_crd)           as adviser_crd,
        any_value(adviser_sec_number)    as adviser_sec_number,
        any_value(adviser_legal_name)    as adviser_legal_name,
        any_value(adviser_business_name) as adviser_business_name
    from era_link
    where adviser_entity_key is not null
    group by accession_number
),

-- Adviser's earliest + latest ADV filing. Earliest powers the
-- "adviser_also_new" proximity bucket; latest carries the most-recent
-- filing_id so the emerging-fund mart can link straight back to it.
era_first_filing as (
    select
        coalesce(firm_crd, sec_adviser_number) as adviser_entity_key,
        min(date_submitted)                    as adviser_first_adv_filing_date,
        max(date_submitted)                    as adviser_latest_adv_filing_date,
        max_by(filing_id, date_submitted)      as adviser_latest_adv_filing_id
    from {{ ref('stg_era_base') }}
    where coalesce(firm_crd, sec_adviser_number) is not null
    group by adviser_entity_key
),

-- ---- Fallback linkage via related_persons ---------------------------------
promoter as (
    select
        accession_number,
        full_name as promoter_name
    from {{ ref('stg_form_d_related_persons') }}
    where is_promoter
    qualify row_number() over (partition by accession_number order by person_seq_key) = 1
)

select
    f.accession_number,
    case
        when e.adviser_entity_key is not null then 'form_adv_join'
        when p.promoter_name      is not null then 'form_d_related_person'
        else 'none'
    end as adviser_source,

    e.adviser_entity_key,
    e.adviser_crd,
    e.adviser_sec_number,
    e.adviser_legal_name,
    e.adviser_business_name,
    eff.adviser_first_adv_filing_date,
    eff.adviser_latest_adv_filing_date,
    eff.adviser_latest_adv_filing_id,

    p.promoter_name as fallback_promoter_name
from filings f
left join era_link_dedup    e   using (accession_number)
left join era_first_filing  eff on e.adviser_entity_key = eff.adviser_entity_key
left join promoter          p   using (accession_number)
