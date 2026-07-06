import os
import json
import pandas as pd
import dlt
from datetime import date
from google.cloud import bigquery
from utils import get_previous_month, get_later_month
from load_raw_to_bq import load_raw_file_to_bq

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")

DATASET_NAME = "broker_dealer"
RAW_TABLE = "broker_dealer_raw"
MASTER_TABLE = "broker_dealer_master"

# dlt normalizes column names to snake_case lowercase, so we work in lowercase
# for everything coming back out of BigQuery.
ENTITY_COLUMNS = ['cik', 'name', 'film_number', 'address', 'address2', 'city', 'state', 'zip']

bq_client = bigquery.Client.from_service_account_info(gcp_credentials)


def read_master():
    table_id = f"{project_id}.{DATASET_NAME}.{MASTER_TABLE}"
    try:
        bq_client.get_table(table_id)
    except Exception:
        print(f'Master table {table_id} not found. Returning empty DataFrame.')
        return pd.DataFrame()
    query = f"SELECT * FROM `{table_id}`"
    return bq_client.query(query).to_dataframe()


def read_raw_for_month(mm, yy):
    file_month = f'{yy}_{mm}'
    cols = ", ".join(ENTITY_COLUMNS)
    query = f"""
        SELECT {cols}
        FROM `{project_id}.{DATASET_NAME}.{RAW_TABLE}`
        WHERE file_month = '{file_month}'
    """
    return bq_client.query(query).to_dataframe()


def write_master(df):
    pipeline = dlt.pipeline(
        pipeline_name="broker_dealer_master_pipeline",
        destination="bigquery",
        dataset_name=DATASET_NAME,
    )
    load_info = pipeline.run(
        df,
        table_name=MASTER_TABLE,
        write_disposition="replace",
        credentials=gcp_credentials,
    )
    print(load_info)


def merge_month(master_df, new_df, file_month):
    """Merge one month's snapshot into the master DataFrame.

    Status transitions:
      absent -> present            New          (start_month stamped)
      present -> present           Active
      Withdrawn -> present         Reregistered (new start_month, original
                                                 withdrawn_month kept)
      present -> absent            Withdrawn    (withdrawn_month stamped on the
                                                 transition month only, never
                                                 overwritten on later months)
    """
    if master_df.empty:
        new_df = new_df.copy()
        new_df['status'] = 'Active'
        new_df['start_month'] = ''
        new_df['withdrawn_month'] = ''
        new_df['last_observed_month'] = file_month
        return new_df

    df_merged = pd.merge(
        new_df,
        master_df,
        on='cik',
        how='outer',
        suffixes=('', '_prev'),
        indicator=True
    )

    for col in list(df_merged.columns):
        if col.endswith('_prev'):
            original_name = col[:-5]
            if original_name in df_merged.columns:
                df_merged[original_name] = df_merged[original_name].fillna(df_merged[col])
                df_merged = df_merged.drop(columns=[col])

    prev_status = df_merged['status'].copy()

    status_map = {
        'left_only': 'New',
        'right_only': 'Withdrawn',
        'both': 'Active'
    }
    # astype(object): .map() on the categorical _merge column yields a
    # Categorical that would reject 'Reregistered' as a new category
    df_merged['status'] = df_merged['_merge'].map(status_map).astype(object)

    reregistered = (df_merged['_merge'] == 'both') & (prev_status == 'Withdrawn')
    df_merged.loc[reregistered, 'status'] = 'Reregistered'
    df_merged.loc[reregistered, 'start_month'] = file_month

    newly_withdrawn = (df_merged['_merge'] == 'right_only') & (prev_status != 'Withdrawn')
    df_merged.loc[newly_withdrawn, 'withdrawn_month'] = file_month

    df_merged = df_merged.drop(columns=['_merge'])
    df_merged.loc[df_merged['status'] == 'New', 'start_month'] = file_month
    df_merged['last_observed_month'] = file_month

    return df_merged


def compare_df(new_mm, new_yy):
    master_df = read_master()
    file_month = f'{new_yy}_{new_mm}'

    # Initialize master from the first available raw month if empty.
    if master_df.empty:
        print('Master table empty. Initializing from raw table.')
        new_df = read_raw_for_month(new_mm, new_yy)
        if new_df.empty:
            print(f'No raw data for {file_month}. Skipping.')
            return None
        return merge_month(master_df, new_df, file_month)

    latest_master_date = master_df['last_observed_month'].max()
    latest_master_year, latest_master_month = latest_master_date.split('_')
    if date(int(new_yy), int(new_mm), 1) <= date(int(latest_master_year), int(latest_master_month), 1):
        print(f'New file {new_mm}/{new_yy} is not newer than the latest master file date {latest_master_date}. No update needed.')
        return master_df

    new_df = read_raw_for_month(new_mm, new_yy)
    if new_df.empty:
        print(f'No raw data for {file_month}. Skipping.')
        return master_df

    return merge_month(master_df, new_df, file_month)


def rebuild_master():
    """Rebuild the master table by replaying every month in the BigQuery raw
    table in order. Repairs status/start_month/withdrawn_month history (e.g.
    after the withdrawn_month overwrite bug). Writes to BigQuery once, at
    the end."""
    query = f"""
        SELECT DISTINCT file_month
        FROM `{project_id}.{DATASET_NAME}.{RAW_TABLE}`
        ORDER BY file_month
    """
    months = [row.file_month for row in bq_client.query(query).result()]
    print(f'Rebuilding master from {len(months)} raw months: {months[0]} -> {months[-1]}')

    master = pd.DataFrame()
    for file_month in months:
        yy, mm = file_month.split('_')
        new_df = read_raw_for_month(mm, yy)
        if new_df.empty:
            print(f'{file_month}: no raw rows, skipping')
            continue
        master = merge_month(master, new_df, file_month)
        print(f'{file_month}: {master["status"].value_counts().to_dict()}')

    write_master(master)
    print(f'Rebuilt master table {DATASET_NAME}.{MASTER_TABLE}')
    return master


def update_monthly(start_month, start_year):
    today = date.today()
    mm = today.strftime("%m")
    yy = today.strftime("%y")

    latest_mm, latest_yy = get_previous_month(mm, yy)

    master_df = read_master()
    if not master_df.empty:
        latest_master_date = master_df['last_observed_month'].max()
        latest_master_month = latest_master_date.split('_')[1]
        latest_master_year = latest_master_date.split('_')[0]
        if date(int(start_year), int(start_month), 1) <= date(int(latest_master_year), int(latest_master_month), 1):
            start_month, start_year = get_later_month(latest_master_month, latest_master_year)

    print(f'Starting update from {start_month}/{start_year} to {latest_mm}/{latest_yy}')
    for yy_iter in range(int(start_year), int(latest_yy) + 1):
        for mm_iter in range(1, 13):
            mm_str = f'{mm_iter:02d}'
            yy_str = f'{yy_iter:02d}'
            if (yy_str == latest_yy) and (mm_str > latest_mm):
                break
            if (yy_str == start_year) and (mm_str < start_month):
                continue

            # Step 1: download raw file locally + ingest to BigQuery raw table
            load_raw_file_to_bq(mm_str, yy_str)

            # Step 2: merge raw into master in BigQuery
            df = compare_df(mm_str, yy_str)
            if df is None or df.empty:
                continue
            print(df.shape)
            write_master(df)
            print(f'Updated master table {DATASET_NAME}.{MASTER_TABLE} for {mm_str}/{yy_str}')


if __name__ == "__main__":
    update_monthly(start_month='02', start_year='26')
