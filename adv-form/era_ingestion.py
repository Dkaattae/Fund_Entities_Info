import os
import dlt
import requests
import zipfile
import io
import pandas as pd
from typing import Iterator
from dotenv import load_dotenv
from datetime import datetime
from dateutil.relativedelta import relativedelta

from util import generate_months
from util import filing_dates
from util import build_url

load_dotenv()


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
            "table": "Address",
            "primary_key": "FilingID"
        },
        f"ERA_Schedule_D_1I_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Website",
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

    CSV_TABLES = generate_csv_table(year, month)

    def load_zip():
        response = requests.get(url)
        response.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(response.content))

    zip_file = load_zip()

    resources = []

    for csv_name, cfg in CSV_TABLES.items():

        @dlt.resource(
            name=cfg["table"],
            primary_key=cfg["primary_key"],
            write_disposition="merge",
        )
        def csv_resource(
            csv_name=csv_name,
        ) -> Iterator[dict]:
            with zip_file.open(csv_name) as f:
                df = pd.read_csv(f, 
                    encoding='utf-8', 
                    encoding_errors='replace', 
                    low_memory=False,
                    on_bad_lines='skip',
                    engine='c')
                for col in df.select_dtypes(include=['object']).columns:
                    df[col] = df[col].astype(str).apply(
                        lambda x: x.encode('utf-8', 'ignore').decode('utf-8')
                    )
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    object_cols = df.select_dtypes(include=['object']).columns
                    df[numeric_cols] = df[numeric_cols].fillna(-1)
                    df[object_cols] = df[object_cols].fillna("None")
                    df = df.copy()
                    df['filing_month'] = f"{year}{month:02d}"
                    yield from df.to_dict(orient="records")

        resources.append(csv_resource)

    return resources

def backfill():
    pipeline = dlt.pipeline(
        pipeline_name="adv_era_filings",
        destination="postgres",
        dataset_name="era_adv",
    )

    for (year, month) in generate_months(12, 1):
        url = build_url(year, month)
        print(f"Loading {url}")
        try:
            info = pipeline.run(
                adv_filing_source(url, year, month),
                loader_file_format="csv",
                write_disposition="merge"
            )
            print(info)
        except requests.exceptions.HTTPError:
            print(f"Data or {year}-{month:02d} not found")


def update_monthly():
    pipeline = dlt.pipeline(
        pipeline_name="adv_era_filings",
        destination="postgres",
        dataset_name="era_adv",
    )

    # 1. Determine the goal: The month before the current month
    last_completed_month = datetime.now() - relativedelta(months=1)
    target_year, target_month = last_completed_month.year, last_completed_month.month

    # 2. Get the last processed month from the DB
    # We use pipeline.sql_client to query the destination directly
    with pipeline.sql_client() as client:
        try:
            query = """
                SELECT 
                    CAST(EXTRACT(YEAR FROM MAX(CAST(date_submitted AS DATE))) AS INTEGER) as year,
                    CAST(EXTRACT(MONTH FROM MAX(CAST(date_submitted AS DATE))) AS INTEGER) as month
                FROM era_adv.base
            """
            with client.execute_query(query) as cursor:
                row = cursor.fetchone()
                if row and row[0] is not None:
                    db_year, db_month = row
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
                loader_file_format="csv",
                write_disposition="merge" # Keeps records unique
            )
            print(info)
        except requests.exceptions.HTTPError:
            print(f"Data for {year}-{month:02d} not found at source.")
        
        current_processing += relativedelta(months=1)


if __name__ == "__main__":
    update_monthly()