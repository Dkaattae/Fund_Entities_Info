import os
import json
import dlt
from dlt.sources.filesystem import filesystem, read_parquet

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")
dataset = "formd_filings"

def load_local_folder_to_bq(folder_path, dataset_name):
    # 1. Create a pipeline
    pipeline = dlt.pipeline(
        pipeline_name="historical_folder_loader_v1",
        destination="bigquery",
        dataset_name=dataset_name
    )

    # 2. Use the filesystem source to grab all .parquet files
    # 'read_parquet' will handle the schema and loading
    local_files = filesystem(bucket_url=folder_path, file_glob="*.parquet")
    
    # 3. Stream the files into BigQuery
    load_info = pipeline.run(
        local_files | read_parquet(), 
        table_name="formd_parsed_leads",
        write_disposition="replace",
        primary_key=["cik", "submission_num"],
        credentials=gcp_credentials
    )
    
    print(f"Historical load finished: {load_info}")

if __name__ == "__main__":
    folder = "./parsed_parquet/"
    load_local_folder_to_bq(folder, dataset)
