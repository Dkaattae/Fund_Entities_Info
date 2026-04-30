with src as (
    select * from {{ source('form_d_filings', 'related_persons') }}
)

select
    accessionnumber                                          as accession_number,
    relatedperson_seq_key                                    as person_seq_key,
    nullif(firstname, '')                                    as first_name,
    nullif(middlename, '')                                   as middle_name,
    nullif(lastname, '')                                     as last_name,
    trim(concat(
        coalesce(nullif(firstname, ''), ''), ' ',
        coalesce(nullif(middlename, ''), ''), ' ',
        coalesce(nullif(lastname, ''), '')
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
    -- Promoter is the relationship that most often points to the adviser /
    -- sponsor entity behind a Form D pooled-fund offering.
    'Promoter' in (
        nullif(relationship_1, ''),
        nullif(relationship_2, ''),
        nullif(relationship_3, '')
    )                                                        as is_promoter
from src
where accessionnumber is not null
