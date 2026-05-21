import os
import dlt
import requests
import zipfile
import io
import json
import pandas as pd
from typing import Iterator
from datetime import datetime
from dateutil.relativedelta import relativedelta
from google.cloud import bigquery

from util import generate_months
from util import filing_dates
from util import build_url
from util import clean_string

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")


def generate_csv_table(year: int, month: int):
    yyyyMMdd = filing_dates(year, month)
    yyyyMM = yyyyMMdd[:-2]
    CSV_TABLES = {
        f"ADV_Filing_Types_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FilingTypes",
            "primary_key": "FilingID",
        },
        f"ERA_ADV_Base_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Base",
            "primary_key": ["FilingID", "DateSubmitted"]
        },
        f"ERA_Schedule_A_B_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Ownership",
            "primary_key": "FilingID",
        },
        f"ERA_Schedule_D_1F_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "AddressTable",
            "primary_key": "FilingID"
        },
        f"ERA_Schedule_D_1I_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "WebsiteTable",
            "primary_key": "FilingID"
        },
        f"ERA_Schedule_D_7A_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Affiliations",
            "primary_key": ["FilingID", "ReferenceID"]
        },
        f"ERA_Schedule_D_7B1_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Funds",
            "primary_key": ["FilingID", "Fund ID", "ReferenceID"]
        },
        f"ERA_Schedule_D_7B1A6b_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Advisor_Fund_Relationships",
            "primary_key": ["FilingID", "ReferenceID", "FundID"]
        },
        f"ERA_Schedule_D_7A_CIK_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "CIKMap",
            "primary_key": ["FilingID", "ReferenceID", "CIK"],
        },
        f"ERA_Schedule_D_7B1A22_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FormDNum",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"ERA_Schedule_D_7B1A23_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Auditors",
            "primary_key": ["FilingID", "ReferenceID", "PCAOB Number"],
        },
        f"ERA_Schedule_D_7B1A24_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Primary_Brokers",
            "primary_key": ["FilingID", "ReferenceID", "SEC Number"],
        },
        f"ERA_Schedule_D_7B1A25_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Custodians",
            "primary_key": ["FilingID", "ReferenceID", "SEC Number"],
        },
        f"ERA_Schedule_D_7B1A26_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FundAdmins",
            "primary_key": ["FilingID", "ReferenceID", "Name of Administrator"],
        },
        f"ERA_Schedule_D_7B1A28_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Marketers",
            "primary_key": ["FilingID", "ReferenceID", "SEC Number"],
        },
    }
    return CSV_TABLES


@dlt.source
def adv_filing_source(url: str, year: int, month: int):
    # 1. Get your table configuration
    CSV_TABLES = generate_csv_table(year, month)

    # 2. Download and open the zip once
    response = requests.get(url)
    response.raise_for_status()
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))

    # 3. Loop through your tables and yield them as resources
    for csv_name, cfg in CSV_TABLES.items():
        
        # We define a generator function for EACH csv file
        def get_rows(name=csv_name, table_cfg=cfg):
            with zip_file.open(name) as f:
                try:
                    df = pd.read_csv(f, low_memory=False, on_bad_lines='skip', encoding='utf-8')
                except UnicodeDecodeError:
                    with zip_file.open(name) as f_retry:
                        df = pd.read_csv(f_retry, low_memory=False, on_bad_lines='skip', encoding='latin-1')
                
                if df.empty:
                    return

                # --- Cleaning Logic ---
                numeric_cols = df.select_dtypes(include=['number']).columns
                object_cols = df.select_dtypes(include=['object']).columns

                # Numbers to Nullable Integers
                df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce').astype('Int64')
                df[numeric_cols] = df[numeric_cols].fillna(-1)
        
                # Strings & Symbols
                df[object_cols] = df[object_cols].fillna("None").astype(str)
                for col in object_cols:
                    df[col] = df[col].apply(clean_string)

                # Metadata
                df = df.copy() # Avoid SettingWithCopyWarning
                df['filing_month'] = f"{year}{month:02d}"

                # Convert to records
                yield df.to_dict(orient='records')

        # 4. Yield the resource with the "Smart Hints" (the shield)
        yield dlt.resource(
            get_rows, # This calls the generator we just defined
            name=cfg["table"],
            primary_key=cfg["primary_key"],
            write_disposition="merge",
            max_table_nesting=0
        )

def backfill():
    pipeline = dlt.pipeline(
        pipeline_name="adv_era_filings",
        destination="bigquery",
        dataset_name="era_adv"
    )

    for (year, month) in generate_months(3, 1):
        url = build_url(year, month)
        print(f"Loading {url}")
        try:
            info = pipeline.run(
                adv_filing_source(url, year, month),
                loader_file_format="parquet",
                write_disposition="merge",
                credentials=gcp_credentials
            )
            print(info)
        except requests.exceptions.HTTPError:
            print(f"Data or {year}-{month:02d} not found")


def update_monthly():
    pipeline = dlt.pipeline(
        pipeline_name="adv_era_filings",
        destination="bigquery",
        dataset_name="era_adv"
    )

    # 1. Determine the goal: The month before the current month
    last_completed_month = datetime.now() - relativedelta(months=1)
    target_year, target_month = last_completed_month.year, last_completed_month.month

    # 2. Get the last processed month from the DB
    bq_client = bigquery.Client.from_service_account_info(gcp_credentials)
    query = f"""
        SELECT
            EXTRACT(YEAR FROM MAX(date_submitted)) as year,
            EXTRACT(MONTH FROM MAX(date_submitted)) as month
        FROM `{project_id}.era_adv.base`
    """
    try:
        row = next(iter(bq_client.query(query).result()))
        if row[0] is not None:
            db_year, db_month = int(row[0]), int(row[1])
            start_date = datetime(db_year, db_month, 1) + relativedelta(months=1)
        else:
            print("No data found in DB. Consider running backfill first.")
            return
    except Exception as e:
        print(f"Table might not exist yet: {e}")
        return

    # 3. Check if we are already up to date
    if start_date > last_completed_month:
        print("Data is already up to date.")
        return

    # 4. Run pipeline for missing months only
    # Assuming generate_months can take a custom range or you can use a while loop
    current_processing = start_date
    while current_processing <= last_completed_month:
        year, month = current_processing.year, current_processing.month
        url = build_url(year, month)
        
        print(f"Updating: {year}-{month:02d}")
        try:
            info = pipeline.run(
                adv_filing_source(url, year, month),
                loader_file_format="parquet",
                write_disposition="merge", # Keeps records unique
                credentials=gcp_credentials
            )
            print(info)
        except requests.exceptions.HTTPError:
            print(f"Data for {year}-{month:02d} not found at source.")
        
        current_processing += relativedelta(months=1)


if __name__ == "__main__":
    backfill()