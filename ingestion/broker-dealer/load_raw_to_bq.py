import os
import json
import dlt
from datetime import date
from utils import load_data, get_previous_month
from download_bd_file import download_file

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)

DATASET_NAME = "broker_dealer"
RAW_TABLE = "broker_dealer_raw"


def load_raw_file_to_bq(mm, yy, file_folder='./files/'):
    file_name = f'bd{mm}01{yy}.txt'
    file_path = os.path.join(file_folder, file_name)

    if not os.path.exists(file_path):
        print(f'File {file_path} not found, downloading...')
        download_file(mm, yy, file_folder=file_folder)

    if not os.path.exists(file_path):
        print(f'File {file_path} still not available. Skipping.')
        return None

    df = load_data(file_path)
    df = df.drop(columns=['na'], errors='ignore')

    file_month = f'{yy}_{mm}'
    df['file_month'] = file_month
    df['source_file'] = file_name

    pipeline = dlt.pipeline(
        pipeline_name="broker_dealer_raw_pipeline",
        destination="bigquery",
        dataset_name=DATASET_NAME,
    )

    load_info = pipeline.run(
        df,
        table_name=RAW_TABLE,
        primary_key=["CIK", "file_month"],
        write_disposition="merge",
        credentials=gcp_credentials,
    )
    print(load_info)
    return df


if __name__ == "__main__":
    today = date.today()
    mm = today.strftime("%m")
    yy = today.strftime("%y")

    # data will be released after the month has passed
    latest_mm, latest_yy = get_previous_month(mm, yy)
    load_raw_file_to_bq(latest_mm, latest_yy)
