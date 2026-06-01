#!/usr/bin/env python3
"""
Finds FUND_ADMIN entries in BigQuery that have no match in seeds/fund_admin_aliases.csv
and appends them as placeholder rows (canonical_name = raw_name).

After running, open seeds/fund_admin_aliases.csv and fill in the correct
canonical_name for each new row, then re-run `dbt run`.

Usage:
    python transform/sec_filings/scripts/discover_unknown_fund_admins.py [--dataset sec_filings]
"""

import argparse
import csv
import json
import os
from pathlib import Path

from google.cloud import bigquery

SEED_PATH = Path(__file__).parent.parent / "seeds" / "fund_admin_aliases.csv"

# Query unknown fund admins: in BigQuery but not matched to any alias.
# alias_canonical_name is NULL when the raw_name had no seed match.
QUERY = """
SELECT
    raw_name,
    COUNT(DISTINCT filing_id) AS filing_count
FROM `{project}.{dataset}.int_service_provider_links`
WHERE provider_type = 'FUND_ADMIN'
  AND alias_canonical_name IS NULL
  AND raw_name IS NOT NULL
GROUP BY raw_name
ORDER BY filing_count DESC, raw_name
"""


def load_seed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["raw_name"].strip().lower() for row in reader}


def append_to_seed(path: Path, new_rows: list[dict]) -> None:
    file_empty = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["raw_name", "canonical_name"])
        if file_empty:
            writer.writeheader()
        for row in new_rows:
            # Placeholder: canonical_name starts as raw_name — edit manually after.
            writer.writerow({"raw_name": row["raw_name"], "canonical_name": row["raw_name"]})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sec_filings", help="BigQuery dataset name")
    args = parser.parse_args()

    creds_json = os.environ.get("BIGQUERY_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise SystemExit("BIGQUERY_SERVICE_ACCOUNT_JSON env var is not set")

    creds = json.loads(creds_json)
    client = bigquery.Client.from_service_account_info(creds)
    project_id = creds["project_id"]

    print(f"Querying {project_id}.{args.dataset}.int_service_provider_links ...")
    rows = list(client.query(QUERY.format(project=project_id, dataset=args.dataset)).result())

    existing = load_seed(SEED_PATH)
    new_rows = [
        {"raw_name": r["raw_name"], "filing_count": r["filing_count"]}
        for r in rows
        if r["raw_name"].strip().lower() not in existing
    ]

    if not new_rows:
        print("No new fund admins found — seed is up to date.")
        return

    print(f"\nFound {len(new_rows)} unmatched fund admins (not in seed):\n")
    for r in new_rows:
        print(f"  {r['filing_count']:>5} filings  {r['raw_name']}")

    append_to_seed(SEED_PATH, new_rows)
    print(f"\nAppended {len(new_rows)} rows to {SEED_PATH}")
    print("Next: open the seed file, set the correct canonical_name for each new row,")
    print("      then run: dbt seed && dbt run -s int_service_provider_links+")


if __name__ == "__main__":
    main()
