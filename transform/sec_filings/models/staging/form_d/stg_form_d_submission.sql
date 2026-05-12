-- Quarterly bulk dataset is the source of truth for historical filings.
-- The daily crawler supplements with filings not yet in a quarterly ZIP.
-- Accession numbers present in the quarterly dataset are excluded from the
-- crawler branch so there are no duplicates.
-- Note: quarterly stores sic_code as INTEGER; crawler stores it as STRING.

with quarterly as (
    select
        accessionnumber                                          as accession_number,
        nullif(trim(file_num), '')                               as file_num,
        safe.parse_date('%d-%b-%Y', nullif(filing_date, ''))     as filing_date,
        cast(sic_code as string)                                 as sic_code,
        nullif(schemaversion, '')                                as schema_version,
        nullif(submissiontype, '')                               as submission_type,
        nullif(testorlive, '')                                   as test_or_live,
        coalesce(over100_personsflag, 0) = 1                     as over_100_persons,
        coalesce(over100_issuerflag, 0)  = 1                     as over_100_issuers,
        nullif(submissiontype, '') in ('D/A')                    as is_amendment_submission
    from {{ source('form_d_filings', 'form_d_submission') }}
    where accessionnumber is not null
),

daily as (
    select
        accessionnumber                                          as accession_number,
        nullif(trim(file_num), '')                               as file_num,
        -- Crawler stores dates in ISO format (YYYY-MM-DD) from the SEC JSON API
        safe.parse_date('%Y-%m-%d', nullif(filing_date, ''))     as filing_date,
        nullif(sic_code, '')                                     as sic_code,
        nullif(schemaversion, '')                                as schema_version,
        nullif(submissiontype, '')                               as submission_type,
        nullif(testorlive, '')                                   as test_or_live,
        false                                                    as over_100_persons,
        false                                                    as over_100_issuers,
        nullif(submissiontype, '') in ('D/A')                    as is_amendment_submission
    from {{ source('formd_crawler', 'form_d_submission') }}
    where accessionnumber is not null
)

select * from quarterly

union all

select d.*
from daily d
left join quarterly q using (accession_number)
where q.accession_number is null
