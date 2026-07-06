"""
Cleanup daily crawler tables after historical backfill.

After running backfill.py for a quarter, run this script to remove
daily records that are now covered by the historical dataset.

It finds the latest filing_date in the historical form_d_submission table,
then deletes all daily records with filing_date <= that date.
"""
import os
import json
from google.cloud import bigquery

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")
if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")
client = bigquery.Client.from_service_account_info(gcp_credentials)

HISTORICAL_DATASET = "form_d_filings"
DAILY_DATASET = "formd_filings_crawler"

# Tables that have accessionnumber as the join key
DAILY_PARSED_TABLES = [
    "form_d_submission",
    "issuer",
    "offering",
    "related_persons",
    "recipients",
    "signatures",
]


def get_historical_cutoff_date():
    """Return the latest filing_date in the historical dataset as a datetime.date.

    Historical filing_date is a 'DD-MON-YYYY' string, so it must be parsed
    before taking MAX (string MAX/comparisons are lexicographic, not
    chronological).
    """
    query = f"""
        SELECT MAX(SAFE.PARSE_DATE('%d-%b-%Y', filing_date)) as max_date
        FROM `{project_id}.{HISTORICAL_DATASET}.form_d_submission`
    """
    max_date = list(client.query(query).result())[0]["max_date"]
    print(f"Latest filing_date in historical dataset: {max_date}")
    return max_date


def get_daily_stats(cutoff_date):
    # Daily filing_date is a 'YYYY-MM-DD' string (SEC submissions API format);
    # parse it so blank/malformed values are kept rather than deleted.
    query = f"""
        SELECT
            COUNT(*) as total,
            COUNTIF(SAFE.PARSE_DATE('%Y-%m-%d', filing_date) <= DATE '{cutoff_date}') as to_delete,
            COUNTIF(SAFE.PARSE_DATE('%Y-%m-%d', filing_date) > DATE '{cutoff_date}') as to_keep
        FROM `{project_id}.{DAILY_DATASET}.form_d_submission`
    """
    result = client.query(query).to_dataframe()
    row = result.iloc[0]
    print(f"Daily form_d_submission: {row['total']} total, "
          f"{row['to_delete']} to delete, {row['to_keep']} to keep")
    return row['to_delete']


def cleanup_parsed_tables(cutoff_date):
    """Delete rows from daily parsed tables where filing_date <= cutoff."""
    # First get the accession numbers to delete, based on form_d_submission dates
    accessions_subquery = f"""
        SELECT accessionnumber
        FROM `{project_id}.{DAILY_DATASET}.form_d_submission`
        WHERE SAFE.PARSE_DATE('%Y-%m-%d', filing_date) <= DATE '{cutoff_date}'
    """

    for table in DAILY_PARSED_TABLES:
        full_table = f"`{project_id}.{DAILY_DATASET}.{table}`"
        # Check if table exists
        try:
            client.get_table(f"{project_id}.{DAILY_DATASET}.{table}")
        except Exception:
            print(f"  Skipping {table} (does not exist)")
            continue

        query = f"""
            DELETE FROM {full_table}
            WHERE accessionnumber IN ({accessions_subquery})
        """
        result = client.query(query).result()
        print(f"  Cleaned {table}: deleted rows with filing_date <= {cutoff_date}")


def cleanup_tracking_table(cutoff_date):
    """Delete or reset tracking rows in formd_daily_submissions."""
    tracking_table = f"`{project_id}.{DAILY_DATASET}.formd_daily_submissions`"

    # The tracking table uses 'date' column (from the daily index), not
    # filing_date, and it is an INT64 in YYYYMMDD form.
    # Delete ALL rows where date <= cutoff regardless of status: those
    # filings are covered by the quarterly bulk dataset, so still-PENDING
    # rows are dead backlog that would otherwise linger forever.
    cutoff_int = int(cutoff_date.strftime("%Y%m%d"))
    query = f"""
        DELETE FROM {tracking_table}
        WHERE date <= {cutoff_int}
    """
    result = client.query(query).result()
    print(f"  Cleaned formd_daily_submissions: deleted rows with date <= {cutoff_date}")


def run_cleanup(dry_run=True):
    cutoff_date = get_historical_cutoff_date()
    if not cutoff_date:
        print("No data in historical dataset. Nothing to clean up.")
        return

    to_delete = get_daily_stats(cutoff_date)

    if dry_run:
        print(f"\n[DRY RUN] Would delete {to_delete} records with filing_date <= {cutoff_date}")
        print("Run with dry_run=False to execute.")
        return

    if to_delete == 0:
        print("No daily parsed records to clean up.")
    else:
        print(f"\nDeleting records with filing_date <= {cutoff_date}...")
        cleanup_parsed_tables(cutoff_date)
    cleanup_tracking_table(cutoff_date)
    print("\nCleanup complete.")


if __name__ == "__main__":
    import sys
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("Running in DRY RUN mode. Pass --execute to actually delete.\n")
    run_cleanup(dry_run=dry_run)
