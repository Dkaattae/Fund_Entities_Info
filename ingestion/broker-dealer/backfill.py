from datetime import date
from load_raw_to_bq import load_raw_file_to_bq


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
    Ingest the raw broker-dealer file for every month between
    (start_month, start_year) and (end_month, end_year), inclusive.

    Years are 2-digit strings (e.g. '24', '26').
    The master is no longer merged here — it is derived in dbt
    (int_broker_dealer_master); run `dbt run --select tag:broker_dealer`
    after a backfill to fold the new months in.
    """
    months = list(iter_months(start_month, start_year, end_month, end_year))
    print(f'Backfilling {len(months)} months: {months[0]} -> {months[-1]}')

    for mm_str, yy_str in months:
        print(f'\n=== {mm_str}/{yy_str} ===')
        raw_df = load_raw_file_to_bq(mm_str, yy_str)
        if raw_df is None:
            print(f'Raw file unavailable for {mm_str}/{yy_str}, skipping.')

    print('\nRaw backfill done. Rebuild the master with: '
          'dbt run --select tag:broker_dealer  (from transform/sec_filings)')


if __name__ == "__main__":
    backfill(start_month='01', start_year='24', end_month='02', end_year='26')
