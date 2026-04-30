"""Run all ADV-form ingestion pipelines together.

Usage:
    python run_all.py              # incremental updates only
    python run_all.py --backfill   # full backfill for all pipelines
"""

import argparse
import sys
import traceback


def run_state_adviser(backfill_mode: bool):
    from state_adviser_ingest import update_daily, backfill
    from datetime import date, timedelta

    if backfill_mode:
        start = date.today() - timedelta(days=7)
        print(f"State adviser: backfilling {start} to today")
        backfill(start)
    else:
        print("State adviser: running daily update")
        update_daily()


def run_era(backfill_mode: bool):
    from era_ingestion import backfill, update_monthly

    if backfill_mode:
        print("ERA: running full backfill")
        backfill()
    else:
        print("ERA: running monthly update")
        update_monthly()


def run_ria(backfill_mode: bool):
    from ria_ingestion import backfill

    # RIA only has backfill (12-month rolling window)
    print("RIA: running backfill")
    backfill()


PIPELINES = [
    ("State Adviser", run_state_adviser),
    ("ERA", run_era),
    ("RIA", run_ria),
]


def main():
    parser = argparse.ArgumentParser(description="Run all ADV-form ingestion pipelines")
    parser.add_argument("--backfill", action="store_true", help="Run full backfill instead of incremental update")
    args = parser.parse_args()

    results = {}
    for name, fn in PIPELINES:
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")
        try:
            fn(args.backfill)
            results[name] = "OK"
        except Exception:
            traceback.print_exc()
            results[name] = "FAILED"

    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for name, status in results.items():
        print(f"  {name}: {status}")

    if any(s == "FAILED" for s in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
