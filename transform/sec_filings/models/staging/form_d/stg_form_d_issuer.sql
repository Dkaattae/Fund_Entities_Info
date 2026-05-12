-- Quarterly: is_primaryissuer_flag is STRING ("YES"/"NO"), cik is INTEGER,
--            yearofinc_value_entered is INTEGER, has both issuer_ and edgar_ previous names.
-- Crawler:   is_primaryissuer_flag is BOOLEAN, cik is STRING,
--            yearofinc_value_entered is STRING, only has edgar_ previous names.

with quarterly_accessions as (
    select accessionnumber
    from {{ source('form_d_filings', 'form_d_submission') }}
),

quarterly as (
    select
        accessionnumber                                                          as accession_number,
        issuer_seq_key,
        upper(coalesce(nullif(is_primaryissuer_flag, ''), 'NO')) = 'YES'        as is_primary_issuer,
        cast(cik as string)                                                      as cik,
        nullif(entityname, '')                                                   as entity_name,
        nullif(street1, '')                                                      as street1,
        nullif(street2, '')                                                      as street2,
        nullif(city, '')                                                         as city,
        nullif(stateorcountry, '')                                               as state_or_country,
        nullif(stateorcountrydescription, '')                                    as state_or_country_description,
        nullif(zipcode, '')                                                      as zip_code,
        nullif(issuerphonenumber, '')                                            as phone,
        nullif(jurisdictionofinc, '')                                            as jurisdiction_of_inc,
        nullif(entitytype, '')                                                   as entity_type,
        nullif(entitytypeotherdesc, '')                                          as entity_type_other,
        nullif(yearofinc_timespan_choice, '')                                    as year_of_inc_choice,
        nullif(yearofinc_value_entered, -1)                                      as year_of_inc,
        -- Quarterly has both issuer_ and edgar_ names; prefer issuer_ then fall back to edgar_
        coalesce(nullif(issuer_previousname_1, ''), nullif(edgar_previousname_1, '')) as previous_name_1,
        coalesce(nullif(issuer_previousname_2, ''), nullif(edgar_previousname_2, '')) as previous_name_2,
        coalesce(nullif(issuer_previousname_3, ''), nullif(edgar_previousname_3, '')) as previous_name_3
    from {{ source('form_d_filings', 'issuer') }}
    where accessionnumber is not null
),

daily as (
    select
        accessionnumber                                                          as accession_number,
        issuer_seq_key,
        coalesce(is_primaryissuer_flag, false)                                   as is_primary_issuer,
        nullif(cik, '')                                                          as cik,
        nullif(entityname, '')                                                   as entity_name,
        nullif(street1, '')                                                      as street1,
        nullif(street2, '')                                                      as street2,
        nullif(city, '')                                                         as city,
        nullif(stateorcountry, '')                                               as state_or_country,
        nullif(stateorcountrydescription, '')                                    as state_or_country_description,
        nullif(zipcode, '')                                                      as zip_code,
        nullif(issuerphonenumber, '')                                            as phone,
        nullif(jurisdictionofinc, '')                                            as jurisdiction_of_inc,
        nullif(entitytype, '')                                                   as entity_type,
        nullif(entity_type_other_desc, '')                                       as entity_type_other,
        nullif(yearofinc_timespan_choice, '')                                    as year_of_inc_choice,
        safe_cast(nullif(yearofinc_value_entered, '') as int64)                  as year_of_inc,
        nullif(edgar_previousname_1, '')                                         as previous_name_1,
        nullif(edgar_previousname_2, '')                                         as previous_name_2,
        nullif(edgar_previousname_3, '')                                         as previous_name_3
    from {{ source('formd_crawler', 'issuer') }}
    where accessionnumber is not null
      and accessionnumber not in (select accessionnumber from quarterly_accessions)
)

select * from quarterly
union all
select * from daily
