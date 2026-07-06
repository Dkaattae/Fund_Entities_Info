import os
import json
import io
from datetime import date, timedelta

import pandas as pd
import requests
import time
import dlt
from google.cloud import bigquery

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")

DATASET = "formd_filings_crawler"

headers = {
    "User-Agent": "HedgeFundNet katechen150621@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}

bq_client = bigquery.Client.from_service_account_info(gcp_credentials)


def _date_to_quarter(d: date) -> tuple[int, int]:
    return d.year, (d.month - 1) // 3 + 1


def formd_by_date(start_date, end_date) -> pd.DataFrame:
    """Fetch Form D/D-A entries from EDGAR daily index files.

    The URL path encodes the year and quarter of each individual date,
    so the range can span a quarter boundary safely.
    """
    business_days = pd.bdate_range(start=start_date, end=end_date, inclusive="left")
    rows = []
    url_template = (
        "https://www.sec.gov/Archives/edgar/daily-index"
        "/{year}/QTR{quarter}/master.{date}.idx"
    )
    for ts in business_days:
        d = ts.date()
        yr, qtr = _date_to_quarter(d)
        date_str = d.strftime("%Y%m%d")
        url = url_template.format(year=yr, quarter=qtr, date=date_str)
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            body = response.text.split(
                "--------------------------------------------------------------------------------"
            )[-1]
            df = pd.read_csv(
                io.StringIO(body),
                sep="|",
                names=["CIK", "Name", "Form", "Date", "Path"],
            )
            target_forms = ["D", "D/A"]
            hits = df[df["Form"].str.strip().str.upper().isin(target_forms)]
            rows.extend(hits.to_dict("records"))
            time.sleep(0.1)
        else:
            print(f"Failed to retrieve data for {date_str}: {response.status_code}")

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["CIK", "Name", "Form", "Date", "Path"]
    )


def get_last_crawled_date() -> date | None:
    """Return the latest date already covered by either dataset.

    Takes the max over the quarterly bulk dataset (filing_date) AND the
    daily tracking table (index date). The tracking table must be included:
    re-crawling an already-fetched day re-merges its rows with
    status='PENDING', which wipes the PARSED statuses and makes the parser
    redo (and re-count) the same filings every run.
    """
    bulk_query = f"""
        SELECT MAX(SAFE.PARSE_DATE('%d-%b-%Y', filing_date)) AS max_date
        FROM `{project_id}.form_d_filings.form_d_submission`
    """
    tracking_query = f"""
        SELECT MAX(SAFE.PARSE_DATE('%Y%m%d', CAST(date AS STRING))) AS max_date
        FROM `{project_id}.{DATASET}.formd_daily_submissions`
    """
    dates = []
    for q in (bulk_query, tracking_query):
        try:
            val = bq_client.query(q).to_dataframe()["max_date"].iloc[0]
        except Exception:
            continue  # table may not exist yet (first bootstrap)
        if not pd.isna(val):
            dates.append(pd.Timestamp(val).date())
    return max(dates) if dates else None


def load_formd_data(start_date: date, end_date: date):
    pipeline = dlt.pipeline(
        pipeline_name="sec_formd_pipeline",
        destination="bigquery",
        dataset_name=DATASET,
    )

    formd_df = formd_by_date(start_date, end_date)
    if formd_df.empty:
        print(f"No Form D filings found between {start_date} and {end_date}.")
        return

    formd_df["status"] = "PENDING"
    formd_df["parsed_at"] = pd.NaT
    formd_df["error_msg"] = None
    formd_df["submission_num"] = formd_df["Path"].apply(
        lambda x: x.split("/")[-1].replace(".txt", "")
    )
    formd_df["accession_clean"] = formd_df["submission_num"].str.replace("-", "")

    load_info = pipeline.run(
        formd_df,
        table_name="formd_daily_submissions",
        primary_key=["CIK", "Path"],
        write_disposition="merge",
        credentials=gcp_credentials,
    )
    print(load_info)


def update_daily():
    """Crawl from the day after the last loaded date up to yesterday."""
    last = get_last_crawled_date()
    today = date.today()

    if last is None:
        # Bootstrap: start from the beginning of the current quarter
        yr, qtr = _date_to_quarter(today)
        start_month = (qtr - 1) * 3 + 1
        start = date(yr, start_month, 1)
        print(f"No existing data. Bootstrapping from {start}.")
    else:
        start = last + timedelta(days=1)

    # Don't try to fetch today — the daily index is published for completed days
    end = today

    if start >= end:
        print(f"Already up to date (last crawled: {last}).")
        return

    print(f"Crawling Form D daily index from {start} to {end} (exclusive).")
    load_formd_data(start, end)


if __name__ == "__main__":
    update_daily()
