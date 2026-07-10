"""Monthly broker-dealer raw loader.

Downloads any missing monthly SEC broker-dealer files and loads them into
the BigQuery raw table (`broker_dealer.broker_dealer_raw`, dlt merge on
cik + file_month). The master table is no longer built here — it is derived
in dbt (`int_broker_dealer_master`, replaying the raw snapshots; migrated
from the pandas merge 2026-07-10, verified column-identical).
"""

import os
import json
from datetime import date

from google.cloud import bigquery
from utils import get_previous_month, get_later_month
from load_raw_to_bq import load_raw_file_to_bq

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")

DATASET_NAME = "broker_dealer"
RAW_TABLE = "broker_dealer_raw"

bq_client = bigquery.Client.from_service_account_info(gcp_credentials)


def latest_raw_month():
    """Return the newest file_month ('yy_mm') in the raw table, or None."""
    query = f"""
        SELECT MAX(file_month) AS latest
        FROM `{project_id}.{DATASET_NAME}.{RAW_TABLE}`
    """
    return next(bq_client.query(query).result()).latest


def update_monthly(start_month, start_year):
    """Load every month from the newest already-loaded raw month (or the
    given start) through the previous calendar month. Re-runs no-op once
    the previous month's file is in the raw table."""
    today = date.today()
    mm = today.strftime("%m")
    yy = today.strftime("%y")

    latest_mm, latest_yy = get_previous_month(mm, yy)

    latest_loaded = latest_raw_month()
    if latest_loaded is not None:
        loaded_yy, loaded_mm = latest_loaded.split('_')
        if date(int(start_year), int(start_month), 1) <= date(int(loaded_yy), int(loaded_mm), 1):
            start_month, start_year = get_later_month(loaded_mm, loaded_yy)

    if date(int(start_year), int(start_month), 1) > date(int(latest_yy), int(latest_mm), 1):
        print(f'Raw table already has {latest_loaded}. Nothing to load.')
        return

    print(f'Loading raw months from {start_month}/{start_year} to {latest_mm}/{latest_yy}')
    for yy_iter in range(int(start_year), int(latest_yy) + 1):
        for mm_iter in range(1, 13):
            mm_str = f'{mm_iter:02d}'
            yy_str = f'{yy_iter:02d}'
            if (yy_str == latest_yy) and (mm_str > latest_mm):
                break
            if (yy_str == start_year) and (mm_str < start_month):
                continue
            load_raw_file_to_bq(mm_str, yy_str)


if __name__ == "__main__":
    update_monthly(start_month='02', start_year='26')
