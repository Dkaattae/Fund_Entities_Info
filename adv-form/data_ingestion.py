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

load_dotenv()


def generate_csv_table(year: int, month: int):
    yyyyMMdd = filing_dates(year, month)
    yyyyMM = yyyyMMdd[:-2]
    CSV_TABLES = {
        f"IA_Schedule_A_B_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Filings",
            "primary_key": "FilingID",
        },
        f"IA_Schedule_D_7B1_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Funds",
            "primary_key": ["FilingID", "Fund ID", "ReferenceID"]
        },
        f"IA_Schedule_D_7B1A6b_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Advisor_Fund_Relationships",
            "primary_key": ["FilingID", "ReferenceID"]
        },
        f"IA_Schedule_D_7A_CIK_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "CIKMap",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"IA_Schedule_D_7B1A22_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FormDNum",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"IA_Schedule_D_7B1A23_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Auditors",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"IA_Schedule_D_7B1A24_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Primary_Brokers",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"IA_Schedule_D_7B1A25_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Custodians",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"IA_Schedule_D_7B1A26_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "FundAdmins",
            "primary_key": ["FilingID", "ReferenceID"],
        },
        f"IA_Schedule_D_7B1A28_{yyyyMM}01_{yyyyMMdd}.csv": {
            "table": "Marketers",
            "primary_key": ["FilingID", "ReferenceID"],
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
                df = pd.read_csv(f, encoding='utf-8', encoding_errors='replace', low_memory=False)
                for col in df.select_dtypes(include=['object']).columns:
                    df[col] = df[col].astype(str).apply(
                        lambda x: x.encode('utf-8', 'ignore').decode('utf-8')
                    )
                    yield from df.to_dict(orient="records")

        resources.append(csv_resource)

    return resources

def backfill():
    pipeline = dlt.pipeline(
        pipeline_name="adv_filings1",
        destination="postgres",
        dataset_name="sec_adv",
    )

    for (year, month) in generate_months(12, 1):
        url = build_url(year, month)
        print(f"Loading {url}")
        try:
            info = pipeline.run(
                adv_filing_source(url, year, month),
                loader_file_format="csv",
                write_disposition="replace"
            )
            print(info)
        except requests.exceptions.HTTPError:
            print(f"Data or {year}-{month:02d} not found")


if __name__ == "__main__":
    backfill()