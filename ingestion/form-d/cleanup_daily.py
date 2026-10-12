"""
Cleanup daily crawler tables after historical backfill.

After running backfill.py for a quarter, run this script to remove
daily records that are now covered by the historical dataset.

It finds which calendar quarters are present in the historical
form_d_submission table, then deletes daily records whose filing_date falls
in one of those quarters. Quarters the bulk data set has NOT loaded (e.g. a
quarter SEC published late or the flow skipped) keep their crawler rows,
since those are the only copy of that quarter's filings.
"""
import os
import json
from functools import lru_cache
from google.cloud import bigquery

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")
if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")


@lru_cache(maxsize=None)
def get_client():
    return bigquery.Client.from_service_account_info(gcp_credentials)


HISTORICAL_DATASET = "form_d_filings"
DAILY_DATASET = "formd_filings_crawler"

# Tables that have accessionnumber as the join key.
# form_d_submission MUST be deleted last: the child-table deletes select
# their accession numbers from it, so deleting it first turns every child
# delete into a no-op and orphans the child rows.
DAILY_PARSED_TABLES = [
    "issuer",
    "offering",
    "related_persons",
    "recipients",
    "signatures",
    "form_d_submission",
]


def get_loaded_quarters():
    """Return the sorted quarter-start dates present in the historical dataset.

    Historical filing_date is a 'DD-MON-YYYY' string, so it must be parsed
    before bucketing (string comparisons are lexicographic, not
    chronological).
    """
    query = f"""
        SELECT DISTINCT DATE_TRUNC(SAFE.PARSE_DATE('%d-%b-%Y', filing_date), QUARTER) AS q
        FROM `{project_id}.{HISTORICAL_DATASET}.form_d_submission`
        WHERE SAFE.PARSE_DATE('%d-%b-%Y', filing_date) IS NOT NULL
        ORDER BY q
    """
    quarters = [row["q"] for row in get_client().query(query).result()]
    print(f"Quarters loaded in historical dataset: {format_quarters(quarters)}")
    return quarters


def format_quarters(quarters):
    return ", ".join(f"{q.year}Q{(q.month - 1) // 3 + 1}" for q in quarters) or "none"


def covered_filter(date_expr, quarters):
    """SQL predicate: date_expr (a DATE) falls in one of the loaded quarters.

    A NULL date_expr (blank/malformed source value) never matches, so those
    rows are kept rather than deleted.
    """
    if not quarters:
        return "FALSE"
    quarter_list = ", ".join(f"DATE '{q.isoformat()}'" for q in quarters)
    return f"DATE_TRUNC({date_expr}, QUARTER) IN ({quarter_list})"


# Daily filing_date is a 'YYYY-MM-DD' string (SEC submissions API format).
DAILY_FILING_DATE = "SAFE.PARSE_DATE('%Y-%m-%d', filing_date)"
# The tracking table's 'date' column is the daily index date, an INT64 YYYYMMDD.
TRACKING_DATE = "SAFE.PARSE_DATE('%Y%m%d', CAST(date AS STRING))"


def get_daily_stats(quarters):
    covered = covered_filter(DAILY_FILING_DATE, quarters)
    query = f"""
        SELECT
            COUNT(*) as total,
            COUNTIF({covered}) as to_delete
        FROM `{project_id}.{DAILY_DATASET}.form_d_submission`
    """
    row = list(get_client().query(query).result())[0]
    print(f"Daily form_d_submission: {row['total']} total, "
          f"{row['to_delete']} to delete, {row['total'] - row['to_delete']} to keep")
    return row['to_delete']


def cleanup_parsed_tables(quarters):
    """Delete rows from daily parsed tables filed in a loaded quarter."""
    # First get the accession numbers to delete, based on form_d_submission dates
    accessions_subquery = f"""
        SELECT accessionnumber
        FROM `{project_id}.{DAILY_DATASET}.form_d_submission`
        WHERE {covered_filter(DAILY_FILING_DATE, quarters)}
    """

    for table in DAILY_PARSED_TABLES:
        full_table = f"`{project_id}.{DAILY_DATASET}.{table}`"
        # Check if table exists
        try:
            get_client().get_table(f"{project_id}.{DAILY_DATASET}.{table}")
        except Exception:
            print(f"  Skipping {table} (does not exist)")
            continue

        query = f"""
            DELETE FROM {full_table}
            WHERE accessionnumber IN ({accessions_subquery})
        """
        get_client().query(query).result()
        print(f"  Cleaned {table}: deleted rows filed in loaded quarters")


def cleanup_tracking_table(quarters):
    """Delete tracking rows in formd_daily_submissions for loaded quarters."""
    tracking_table = f"`{project_id}.{DAILY_DATASET}.formd_daily_submissions`"

    # Delete ALL rows in a loaded quarter regardless of status: those
    # filings are covered by the quarterly bulk dataset, so still-PENDING
    # rows are dead backlog that would otherwise linger forever. Rows in
    # unloaded quarters stay so the crawler keeps them.
    query = f"""
        DELETE FROM {tracking_table}
        WHERE {covered_filter(TRACKING_DATE, quarters)}
    """
    get_client().query(query).result()
    print("  Cleaned formd_daily_submissions: deleted rows dated in loaded quarters")


def run_cleanup(dry_run=True):
    quarters = get_loaded_quarters()
    if not quarters:
        print("No data in historical dataset. Nothing to clean up.")
        return

    to_delete = get_daily_stats(quarters)

    if dry_run:
        print(f"\n[DRY RUN] Would delete {to_delete} records filed in {format_quarters(quarters)}")
        print("Run with dry_run=False to execute.")
        return

    if to_delete == 0:
        print("No daily parsed records to clean up.")
    else:
        print("\nDeleting records filed in loaded quarters...")
        cleanup_parsed_tables(quarters)
    cleanup_tracking_table(quarters)
    print("\nCleanup complete.")


if __name__ == "__main__":
    import sys
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("Running in DRY RUN mode. Pass --execute to actually delete.\n")
    run_cleanup(dry_run=dry_run)
