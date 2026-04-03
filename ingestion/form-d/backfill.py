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

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")

url_template = 'https://www.sec.gov/files/structureddata/data/form-d-data-sets/{year}q{quarter}_d.zip'

headers = {
    'User-Agent': 'HedgeFundNet katechen150621@gmail.com',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

def generate_quarters(start_year=2025, start_quarter=1, quarter_cnt=None):
    current_year = datetime.now().year
    current_quarter = (datetime.now().month - 1) // 3 + 1

    quarters = []
    year, quarter = start_year, start_quarter
    while (year < current_year) or (year == current_year and quarter < current_quarter):
        if quarter_cnt and len(quarters) >= quarter_cnt:
            break
        quarters.append((year, quarter))
        quarter += 1
        if quarter > 4:
            quarter = 1
            year += 1

    return quarters

def generate_tsv_table():
    tsv_tables = {
        "RECIPIENTS.tsv": {
            "table": "Recipients",
            "primary_key": ["ACCESSIONNUMBER", "RECIPIENT_SEQ_KEY"],
        },
        "OFFERING.tsv": {
            "table": "Offering",
            "primary_key": "ACCESSIONNUMBER",
        },
        "ISSUERS.tsv": {
            "table": "Issuer",
            "primary_key": ["ACCESSIONNUMBER", "ISSUER_SEQ_KEY"],
        },
        "RELATEDPERSONS.tsv": {
            "table": "RelatedPersons",
            "primary_key": ["ACCESSIONNUMBER", "RELATEDPERSON_SEQ_KEY"],
        },
        "FORMDSUBMISSION.tsv": {
            "table": "FormDSubmission",
            "primary_key": ["ACCESSIONNUMBER", "FILE_NUM"],
        },
        "SIGNATURES.tsv": {
            "table": "Signatures",
            "primary_key": ["ACCESSIONNUMBER", "SIGNATURE_SEQ_KEY"],
        }
    }
    return tsv_tables


@dlt.source
def form_d_source(url: str, year: int, quarter: int):
    # 1. Get your table configuration
    TSV_TABLES = generate_tsv_table()

    # 2. Download and open the zip once
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    # print(zip_file.namelist())
    # 3. Loop through your tables and yield them as resources
    for tsv_name, cfg in TSV_TABLES.items():
        # We define a generator function for EACH tsv file
        def get_rows(name=tsv_name, table_cfg=cfg):
            filename = f"{year}Q{quarter}_d/{name}"
            # print(f"Processing {filename} for table {table_cfg['table']}")
            with zip_file.open(filename) as f:
                try:
                    df = pd.read_csv(f, sep='\t', low_memory=False, on_bad_lines='skip', encoding='utf-8')
                except UnicodeDecodeError:
                    with zip_file.open(filename) as f_retry:
                        df = pd.read_csv(f_retry, sep='\t', low_memory=False, on_bad_lines='skip', encoding='latin-1')
                
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

def backfill(start_year, start_quarter, quarter_cnt=None):
    pipeline = dlt.pipeline(
        pipeline_name="form_d_filings_backfill",
        destination="bigquery",
        dataset_name="form_d_filings"
    )

    for (year, quarter) in generate_quarters(start_year=start_year, 
                start_quarter=start_quarter, quarter_cnt=quarter_cnt):
        url = url_template.format(year=year, quarter=quarter)
        print(f"Loading {url}")
        try:
            info = pipeline.run(
                form_d_source(url, year, quarter),
                loader_file_format="parquet",
                write_disposition="merge",
                credentials=gcp_credentials
            )
            print(info)
        except requests.exceptions.HTTPError as e:
            print(f"Data of {year}-q{quarter} not found with error {e}")


if __name__ == "__main__":
    backfill(start_year=2025, start_quarter=1)