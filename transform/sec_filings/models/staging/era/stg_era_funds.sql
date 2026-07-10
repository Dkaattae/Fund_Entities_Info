with src as (
    select * from {{ source('era_adv', 'funds') }}
)

-- Schedule D 7.B.1 private funds, one row per (filing_id, fund_id).
-- The audit block (annual_audit -> fs_distributed / unqualified_opinion /
-- gaap) is gated: the follow-up answers are 'None' exactly when
-- annual_audit = 'N', so audited rows always carry real answers.
select
    filing_id,
    reference_id,
    nullif(fund_id, 'None')                        as fund_id,
    nullif(trim(fund_name), 'None')                as fund_name,
    nullif(fund_type, 'None')                      as fund_type,
    nullif(state, 'None')                          as state,
    nullif(country, 'None')                        as country,
    gross_asset_value,
    nullif(fund_of_funds, 'None') = 'Y'            as is_fund_of_funds,
    nullif(master_fund, 'None') = 'Y'              as is_master_fund,
    nullif(feeder_fund, 'None') = 'Y'              as is_feeder_fund,
    nullif(annual_audit, 'None') = 'Y'             as is_audited,
    case nullif(gaap, 'None')
        when 'Y' then true when 'N' then false
    end                                            as is_gaap,
    case nullif(fs_distributed, 'None')
        when 'Y' then true when 'N' then false
    end                                            as fs_distributed,
    -- 'Yes' / 'No' / 'Report Not Yet Received'
    nullif(unqualified_opinion, 'None')            as audit_opinion,
    filing_month
from src
where filing_id is not null
