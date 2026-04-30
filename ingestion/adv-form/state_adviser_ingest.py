"""Ingest IA_FIRM_STATE feed into BigQuery.

Workflow (mirrors broker-dealer pattern):
  1. Download daily XML snapshot
  2. Parse into firms + registrations DataFrames
  3. Load raw snapshot to BigQuery (merge on firm_crd + snapshot_date)
  4. Merge into master table tracking status over time
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
MASTER_TABLE = "state_adviser_master"

ENTITY_COLUMNS = [
    "firm_crd", "business_name", "legal_name", "umbrella_registration",
    "main_street1", "main_street2", "main_city", "main_state",
    "main_country", "main_postal_code", "main_phone",
    "filing_date", "form_version", "org_form", "fiscal_year_end",
    "state_of_org", "country_of_org", "total_employees",
    "aum_discretionary", "aum_non_discretionary", "aum_total",
    "account_count", "websites",
]

bq_client = bigquery.Client.from_service_account_info(gcp_credentials)


# ---------------------------------------------------------------------------
# Raw loading
# ---------------------------------------------------------------------------

def load_raw_to_bq(dt: date):
    """Download, parse, and load raw snapshot for the given date."""
    xml_path = download_file(dt)
    if xml_path is None:
        print(f"No XML available for {dt}. Skipping.")
        return None, None

    firms_df, reg_df = parse_xml(xml_path)
    print(f"Parsed {len(firms_df)} firms, {len(reg_df)} registrations for {dt}")

    pipeline = dlt.pipeline(
        pipeline_name="state_adviser_raw_pipeline",
        destination="bigquery",
        dataset_name=DATASET,
    )

    # Load firms raw
    load_info = pipeline.run(
        firms_df,
        table_name=RAW_FIRMS_TABLE,
        primary_key=["firm_crd", "snapshot_date"],
        write_disposition="merge",
        credentials=gcp_credentials,
    )
    print(load_info)

    # Load registrations raw
    load_info = pipeline.run(
        reg_df,
        table_name=RAW_REGISTRATIONS_TABLE,
        primary_key=["firm_crd", "regulator_state", "registration_type", "snapshot_date"],
        write_disposition="merge",
        credentials=gcp_credentials,
    )
    print(load_info)

    return firms_df, reg_df


# ---------------------------------------------------------------------------
# Master table logic
# ---------------------------------------------------------------------------

def read_master() -> pd.DataFrame:
    table_id = f"{project_id}.{DATASET}.{MASTER_TABLE}"
    try:
        bq_client.get_table(table_id)
    except Exception:
        print(f"Master table {table_id} not found. Returning empty DataFrame.")
        return pd.DataFrame()
    query = f"SELECT * FROM `{table_id}`"
    return bq_client.query(query).to_dataframe()


def write_master(df: pd.DataFrame):
    pipeline = dlt.pipeline(
        pipeline_name="state_adviser_master_pipeline",
        destination="bigquery",
        dataset_name=DATASET,
    )
    load_info = pipeline.run(
        df,
        table_name=MASTER_TABLE,
        write_disposition="replace",
        credentials=gcp_credentials,
    )
    print(load_info)


def read_raw_firms_for_date(dt: date) -> pd.DataFrame:
    snapshot_str = dt.strftime("%Y-%m-%d")
    cols = ", ".join(ENTITY_COLUMNS)
    query = f"""
        SELECT {cols}
        FROM `{project_id}.{DATASET}.{RAW_FIRMS_TABLE}`
        WHERE snapshot_date = '{snapshot_str}'
    """
    return bq_client.query(query).to_dataframe()


def merge_snapshot(dt: date):
    """Merge a daily snapshot into the master table."""
    master_df = read_master()
    snapshot_str = dt.strftime("%Y-%m-%d")

    if master_df.empty:
        print("Master table empty. Initializing from raw snapshot.")
        new_df = read_raw_firms_for_date(dt)
        if new_df.empty:
            print(f"No raw data for {dt}. Skipping.")
            return None
        new_df["status"] = "Active"
        new_df["first_seen_date"] = snapshot_str
        new_df["withdrawn_date"] = ""
        new_df["last_observed_date"] = snapshot_str
        return new_df

    latest_date = master_df["last_observed_date"].max()
    if snapshot_str <= latest_date:
        print(f"Snapshot {snapshot_str} not newer than master ({latest_date}). Skipping.")
        return master_df

    new_df = read_raw_firms_for_date(dt)
    if new_df.empty:
        print(f"No raw data for {dt}. Skipping.")
        return master_df

    df_merged = pd.merge(
        new_df,
        master_df,
        on="firm_crd",
        how="outer",
        suffixes=("", "_prev"),
        indicator=True,
    )

    # Fill missing values from previous master row
    for col in list(df_merged.columns):
        if col.endswith("_prev"):
            original = col[:-5]
            if original in df_merged.columns:
                df_merged[original] = df_merged[original].fillna(df_merged[col])
                df_merged = df_merged.drop(columns=[col])

    status_map = {
        "left_only": "New",
        "right_only": "Withdrawn",
        "both": "Active",
    }
    df_merged["status"] = df_merged["_merge"].map(status_map)
    df_merged = df_merged.drop(columns=["_merge"])

    df_merged.loc[df_merged["status"] == "New", "first_seen_date"] = snapshot_str
    df_merged.loc[df_merged["status"] == "Withdrawn", "withdrawn_date"] = snapshot_str
    df_merged["last_observed_date"] = snapshot_str

    return df_merged


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def ingest_date(dt: date):
    """Full pipeline for a single date: download -> raw -> merge master."""
    print(f"\n=== Processing {dt} ===")
    firms_df, _ = load_raw_to_bq(dt)
    if firms_df is None:
        print(f"No data for {dt}. Skipping.")
        return

    master_df = merge_snapshot(dt)
    if master_df is None or master_df.empty:
        return
    print(f"Master table: {master_df.shape}")
    write_master(master_df)
    print(f"Updated master for {dt}")


def backfill(start_date: date, end_date: date | None = None):
    """Backfill from start_date to end_date (inclusive), trying each day.

    The SEC feed is only available for recent dates (~7 days), so dates
    outside that window will be skipped automatically.
    """
    if end_date is None:
        end_date = date.today()

    dt = start_date
    while dt <= end_date:
        ingest_date(dt)
        dt += timedelta(days=1)


def get_latest_raw_date() -> date | None:
    """Query BQ for the most recent snapshot_date in the raw firms table."""
    table_id = f"{project_id}.{DATASET}.{RAW_FIRMS_TABLE}"
    try:
        bq_client.get_table(table_id)
    except Exception:
        return None
    query = f"SELECT MAX(snapshot_date) as max_date FROM `{table_id}`"
    result = bq_client.query(query).to_dataframe()
    val = result["max_date"].iloc[0]
    if pd.isna(val):
        return None
    return pd.Timestamp(val).date()


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
