from datetime import date
from load_raw_to_bq import load_raw_file_to_bq
from merge_files import compare_df, write_master, DATASET_NAME, MASTER_TABLE


def iter_months(start_month, start_year, end_month, end_year):
    """Yield (mm_str, yy_str) tuples from start to end inclusive."""
    start = date(int(f'20{start_year}'), int(start_month), 1)
    end = date(int(f'20{end_year}'), int(end_month), 1)
    if start > end:
        raise ValueError(f'start {start} is after end {end}')

    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        yield f'{m:02d}', f'{y % 100:02d}'
        m += 1
        if m > 12:
            m = 1
            y += 1


def backfill(start_month, start_year, end_month, end_year):
    """
    Run the broker-dealer pipeline for every month between
    (start_month, start_year) and (end_month, end_year), inclusive.

    Years are 2-digit strings (e.g. '24', '26').
    For each month it (1) ingests the raw file into the BigQuery raw table,
    then (2) merges it into the master table.
    """
    months = list(iter_months(start_month, start_year, end_month, end_year))
    print(f'Backfilling {len(months)} months: {months[0]} -> {months[-1]}')

    for mm_str, yy_str in months:
        print(f'\n=== {mm_str}/{yy_str} ===')

        # Step 1: download raw file locally + ingest to BigQuery raw table
        raw_df = load_raw_file_to_bq(mm_str, yy_str)
        if raw_df is None:
            print(f'Raw file unavailable for {mm_str}/{yy_str}, skipping merge.')
            continue

        # Step 2: merge raw into master in BigQuery
        df = compare_df(mm_str, yy_str)
        if df is None or df.empty:
            print(f'No data merged for {mm_str}/{yy_str}.')
            continue
        print(df.shape)
        write_master(df)
        print(f'Updated master table {DATASET_NAME}.{MASTER_TABLE} for {mm_str}/{yy_str}')


if __name__ == "__main__":
    backfill(start_month='01', start_year='24', end_month='02', end_year='26')
