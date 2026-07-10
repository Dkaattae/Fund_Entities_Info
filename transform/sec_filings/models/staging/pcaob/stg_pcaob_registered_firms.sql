-- One row per PCAOB firm_id — the complete registered-firms directory,
-- including withdrawn/revoked/disapproved firms. A reported PCAOB number
-- still identifies the firm after it deregisters (same reasoning as
-- withdrawn broker-dealers in the BD master), so identity validation joins
-- against ALL rows and keeps registration_status as an attribute.

select
    firm_id,
    firm_name,
    firm_other_name,
    firm_predecessor_name,
    city,
    state,
    country,
    headquarters_address,
    registration_status,
    registration_date,
    audit_report_activity,
    is_subject_to_hfcaa
from {{ source('pcaob', 'registered_firms') }}
