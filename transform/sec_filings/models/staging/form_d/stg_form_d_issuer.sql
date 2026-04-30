with src as (
    select * from {{ source('form_d_filings', 'issuer') }}
)

select
    accessionnumber                                              as accession_number,
    issuer_seq_key,
    upper(coalesce(nullif(is_primaryissuer_flag, ''), 'NO')) = 'YES' as is_primary_issuer,
    cik,
    nullif(entityname, '')                                       as entity_name,
    nullif(street1, '')                                          as street1,
    nullif(street2, '')                                          as street2,
    nullif(city, '')                                             as city,
    nullif(stateorcountry, '')                                   as state_or_country,
    nullif(stateorcountrydescription, '')                        as state_or_country_description,
    nullif(zipcode, '')                                          as zip_code,
    nullif(issuerphonenumber, '')                                as phone,
    nullif(jurisdictionofinc, '')                                as jurisdiction_of_inc,
    nullif(entitytype, '')                                       as entity_type,
    nullif(entitytypeotherdesc, '')                              as entity_type_other,
    nullif(yearofinc_timespan_choice, '')                        as year_of_inc_choice,
    nullif(yearofinc_value_entered, -1)                          as year_of_inc,
    nullif(issuer_previousname_1, '')                            as previous_name_1,
    nullif(issuer_previousname_2, '')                            as previous_name_2,
    nullif(issuer_previousname_3, '')                            as previous_name_3
from src
where accessionnumber is not null
