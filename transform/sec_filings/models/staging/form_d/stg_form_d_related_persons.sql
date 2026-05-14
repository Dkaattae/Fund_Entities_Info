-- Explicit column selection prevents UNION ALL failures from differing
-- physical column order between the quarterly and crawler BQ tables.

with quarterly_accessions as (
    select accessionnumber
    from {{ source('form_d_filings', 'form_d_submission') }}
),

quarterly as (
    select
        accessionnumber,
        relatedperson_seq_key,
        firstname,
        middlename,
        lastname,
        street1,
        street2,
        city,
        stateorcountry,
        stateorcountrydescription,
        zipcode,
        relationship_1,
        relationship_2,
        relationship_3,
        relationshipclarification
    from {{ source('form_d_filings', 'related_persons') }}
    where accessionnumber is not null
),

daily as (
    select
        accessionnumber,
        relatedperson_seq_key,
        firstname,
        middlename,
        lastname,
        street1,
        street2,
        city,
        stateorcountry,
        stateorcountrydescription,
        zipcode,
        relationship_1,
        relationship_2,
        relationship_3,
        relationshipclarification
    from {{ source('formd_crawler', 'related_persons') }}
    where accessionnumber is not null
      and accessionnumber not in (select accessionnumber from quarterly_accessions)
),

src as (
    select * from quarterly
    union all
    select * from daily
)

select
    accessionnumber                                          as accession_number,
    relatedperson_seq_key                                    as person_seq_key,
    nullif(firstname, '')                                    as first_name,
    nullif(middlename, '')                                   as middle_name,
    nullif(lastname, '')                                     as last_name,
    -- Build full_name, treating 'N/A' and 'NA' (any case) as missing
    trim(regexp_replace(
        concat(
            coalesce(
                case when regexp_contains(trim(firstname), r'(?i)^n\/?a$') then null
                     else nullif(trim(firstname), '') end,
                ''), ' ',
            coalesce(
                case when regexp_contains(trim(middlename), r'(?i)^n\/?a$') then null
                     else nullif(trim(middlename), '') end,
                ''), ' ',
            coalesce(
                case when regexp_contains(trim(lastname), r'(?i)^n\/?a$') then null
                     else nullif(trim(lastname), '') end,
                '')
        ),
        r'\s{2,}', ' '
    ))                                                       as full_name,
    nullif(street1, '')                                      as street1,
    nullif(street2, '')                                      as street2,
    nullif(city, '')                                         as city,
    nullif(stateorcountry, '')                               as state_or_country,
    nullif(stateorcountrydescription, '')                    as state_or_country_description,
    nullif(zipcode, '')                                      as zip_code,
    nullif(relationship_1, '')                               as relationship_1,
    nullif(relationship_2, '')                               as relationship_2,
    nullif(relationship_3, '')                               as relationship_3,
    nullif(relationshipclarification, '')                    as relationship_clarification,
    'Promoter' in (
        nullif(relationship_1, ''),
        nullif(relationship_2, ''),
        nullif(relationship_3, '')
    )                                                        as is_promoter
from src
