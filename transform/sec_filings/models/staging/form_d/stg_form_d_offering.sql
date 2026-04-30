with src as (
    select * from {{ source('form_d_filings', 'offering') }}
),

cleaned as (
    select
        accessionnumber                                          as accession_number,
        nullif(industrygrouptype, '')                            as industry_group_type,
        nullif(investmentfundtype, '')                           as investment_fund_type,
        nullif(is40_act, '')                                     as is_40_act,
        nullif(revenuerange, '')                                 as revenue_range,
        nullif(aggregatenetassetvaluerange, '')                  as aggregate_nav_range,
        upper(coalesce(federalexemptions_items_list, ''))        as federal_exemptions_raw,
        coalesce(isamendment, false)                             as is_amendment,
        nullif(previousaccessionnumber, '')                      as previous_accession_number,
        safe.parse_date('%Y-%m-%d', nullif(sale_date, ''))       as sale_date,
        upper(coalesce(yettooccur, '')) = 'TRUE'                 as first_sale_yet_to_occur,
        coalesce(morethanoneyear, false)                         as offering_more_than_one_year,
        nullif(minimuminvestmentaccepted, -1)                    as minimum_investment_accepted,
        coalesce(over100_recipientflag, 0) = 1                   as over_100_recipients,
        nullif(totalofferingamount, '')                          as total_offering_amount_raw,
        safe_cast(nullif(totalofferingamount, '') as numeric)    as total_offering_amount_numeric,
        nullif(totalamountsold, -1)                              as total_amount_sold,
        nullif(totalremaining, '')                               as total_remaining_raw,
        safe_cast(nullif(totalremaining, '') as numeric)         as total_remaining_numeric,
        coalesce(hasnonaccreditedinvestors, false)               as has_non_accredited_investors,
        nullif(numbernonaccreditedinvestors, -1)                 as number_non_accredited_investors,
        nullif(totalnumberalreadyinvested, -1)                   as number_already_invested,
        nullif(salescomm_dollaramount, -1)                       as sales_commission_amount,
        nullif(findersfee_dollaramount, -1)                      as finders_fee_amount,
        nullif(grossproceedsused_dollaramount, -1)               as gross_proceeds_used_amount,
        coalesce(ispooledinvestmentfundtype, '')                 as security_pooled_investment_fund_flag,
        coalesce(isequitytype, '')                               as security_equity_flag,
        coalesce(isdebttype, '')                                 as security_debt_flag
    from src
    where accessionnumber is not null
)

select
    *,
    -- Federal exemption flags parsed from comma-list "06b, 3C, 3C.7"
    regexp_contains(federal_exemptions_raw, r'(^|[, ])3C\.1([, ]|$)') as claims_3c1,
    regexp_contains(federal_exemptions_raw, r'(^|[, ])3C\.7([, ]|$)') as claims_3c7,
    regexp_contains(federal_exemptions_raw, r'(^|[, ])06B([, ]|$)')   as claims_506b,
    regexp_contains(federal_exemptions_raw, r'(^|[, ])06C([, ]|$)')   as claims_506c
from cleaned
