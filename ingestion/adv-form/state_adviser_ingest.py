"""Ingest IA_FIRM_STATE feed into BigQuery.

Workflow:
  1. Download daily XML snapshot
  2. Parse into firms + registrations DataFrames
  3. Load raw snapshot to BigQuery (merge on firm_crd + snapshot_date)

All derived state (current status, first seen, withdrawn, AUM history) is
computed in dbt from the raw tables — no master table is maintained here.
"""

import os
import json
import dlt
import pandas as pd
from datetime import date, timedelta
from google.cloud import bigquery

from state_adviser_download import download_file, find_latest_available
from state_adviser_parse import parse_xml

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")
if not service_account_json_str:
    raise ValueError("BIGQUERY_SERVICE_ACCOUNT_JSON not set.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")

DATASET = "state_adviser"
RAW_FIRMS_TABLE = "state_adviser_firms_raw"
RAW_REGISTRATIONS_TABLE = "state_adviser_registrations_raw"

bq_client = bigquery.Client.from_service_account_info(gcp_credentials)


# ---------------------------------------------------------------------------
# Raw loading
# ---------------------------------------------------------------------------

def load_raw_to_bq(dt: date) -> bool:
    """Download, parse, and load raw snapshot for the given date.
    Returns True if data was loaded, False if skipped."""
    xml_path = download_file(dt)
    if xml_path is None:
        print(f"No XML available for {dt}. Skipping.")
        return False

    firms_df, reg_df = parse_xml(xml_path)
    print(f"Parsed {len(firms_df)} firms, {len(reg_df)} registrations for {dt}")

    pipeline = dlt.pipeline(
        pipeline_name="state_adviser_raw_pipeline",
        destination="bigquery",
        dataset_name=DATASET,
    )

    load_info = pipeline.run(
        firms_df,
        table_name=RAW_FIRMS_TABLE,
        primary_key=["firm_crd", "snapshot_date"],
        write_disposition="merge",
        credentials=gcp_credentials,
    )
    print(load_info)

    load_info = pipeline.run(
        reg_df,
        table_name=RAW_REGISTRATIONS_TABLE,
        primary_key=["firm_crd", "regulator_state", "registration_type", "snapshot_date"],
        write_disposition="merge",
        credentials=gcp_credentials,
    )
    print(load_info)

    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def get_latest_raw_date() -> date | None:
    """Query BQ for the most recent snapshot_date in the raw firms table."""
    table_id = f"{project_id}.{DATASET}.{RAW_FIRMS_TABLE}"
    try:
        bq_client.get_table(table_id)
    except Exception:
        return None
    result = bq_client.query(
        f"SELECT MAX(snapshot_date) as max_date FROM `{table_id}`"
    ).to_dataframe()
    val = result["max_date"].iloc[0]
    if pd.isna(val):
        return None
    return pd.Timestamp(val).date()


def ingest_date(dt: date):
    """Full pipeline for a single date: download → raw BQ load."""
    print(f"\n=== Processing {dt} ===")
    load_raw_to_bq(dt)


def backfill(start_date: date, end_date: date | None = None):
    """Backfill from start_date to end_date (inclusive)."""
    if end_date is None:
        end_date = date.today()
    dt = start_date
    while dt <= end_date:
        ingest_date(dt)
        dt += timedelta(days=1)


def update_daily():
    """Check BQ for the last ingested date, then backfill any gap to today."""
    latest_available = find_latest_available()
    if latest_available is None:
        print("No recent feed found on SEC.")
        return

    last_in_bq = get_latest_raw_date()
    if last_in_bq is None:
        print("No existing data in BQ. Running latest available date only.")
        ingest_date(latest_available)
        return

    start = last_in_bq + timedelta(days=1)
    if start > latest_available:
        print(f"Already up to date (last in BQ: {last_in_bq}, latest on SEC: {latest_available}).")
        return

    print(f"Last in BQ: {last_in_bq}. Backfilling {start} to {latest_available}.")
    backfill(start, latest_available)


if __name__ == "__main__":
    update_daily()
