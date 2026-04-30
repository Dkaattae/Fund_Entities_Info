with src as (
    select * from {{ source('form_d_filings', 'form_d_submission') }}
)

select
    accessionnumber                                          as accession_number,
    nullif(trim(file_num), '')                               as file_num,
    safe.parse_date('%d-%b-%Y', nullif(filing_date, ''))     as filing_date,
    sic_code,
    nullif(schemaversion, '')                                as schema_version,
    nullif(submissiontype, '')                               as submission_type,
    nullif(testorlive, '')                                   as test_or_live,
    coalesce(over100_personsflag, 0) = 1                     as over_100_persons,
    coalesce(over100_issuerflag, 0)  = 1                     as over_100_issuers,
    nullif(submissiontype, '') in ('D/A')                    as is_amendment_submission
from src
where accessionnumber is not null
