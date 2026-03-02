import os
import dlt
import requests
import zipfile
import io
import pandas as pd
from typing import Iterator
from dotenv import load_dotenv

from util import generate_months
from util import filing_dates
from util import build_url
from util import clean_string

load_dotenv()


def generate_csv_table(year: int, month: int):
    yyyyMMdd = filing_dates(year, month)
    yyyyMM = yyyyMMdd[:-2]
    CSV_TABLES = {
        f"ADV_Filing_Types_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FilingTypes",
            "primary_key": "FilingID",
        },
        f"IA_ADV_Base_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Base",
            "primary_key": ["FilingID", "DateSubmitted"]
        },
        f"IA_Schedule_A_B_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Ownership",
            "primary_key": "FilingID",
        },
        f"IA_Schedule_D_1F_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Address",
            "primary_key": "FilingID"
        },
        f"IA_Schedule_D_1I_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Website",
            "primary_key": "FilingID"
        },
        f"IA_Schedule_D_7A_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Affiliations",
            "primary_key": ["FilingID", "ReferenceID"]
        },
        f"IA_Schedule_D_7B1_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Funds",
            "primary_key": ["FilingID", "Fund ID", "ReferenceID"]
        },
        f"IA_Schedule_D_7B1A6b_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Advisor_Fund_Relationships",
            "primary_key": ["FilingID", "ReferenceID", "FundID"]
        },
        f"IA_Schedule_D_7A_CIK_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "CIKMap",
            "primary_key": ["FilingID", "ReferenceID", "CIK"],
        },
        f"IA_Schedule_D_7B1A22_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FormDNum",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"IA_Schedule_D_7B1A23_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Auditors",
            "primary_key": ["FilingID", "ReferenceID", "PCAOB Number"],
        },
        f"IA_Schedule_D_7B1A24_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Primary_Brokers",
            "primary_key": ["FilingID", "ReferenceID", "SEC Number"],
        },
        f"IA_Schedule_D_7B1A25_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Custodians",
            "primary_key": ["FilingID", "ReferenceID", "SEC Number"],
        },
        f"IA_Schedule_D_7B1A26_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FundAdmins",
            "primary_key": ["FilingID", "ReferenceID", "Name of Administrator"],
        },
        f"IA_Schedule_D_7B1A28_{yyyyMM}01_{yyyyMMdd}.csv": {
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
        pipeline_name="adv_ria_filings",
        destination="bigquery",
        dataset_name="ria_adv",
        credentials=gcp_credentials
    )

    for (year, month) in generate_months(12, 1):
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


if __name__ == "__main__":
    backfill()