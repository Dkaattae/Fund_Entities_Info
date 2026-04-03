import os
import json
from google.cloud import bigquery
import pandas as pd

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)

class BigQueryHandler:
    def __init__(self, project_id, dataset, credentials_path=gcp_credentials):
        self.client = bigquery.Client.from_service_account_info(gcp_credentials)
        self.project = project_id
        self.dataset = dataset

    def get_pending_submissions(self, table_name="formd_daily_submissions", limit=1000):
        """Fetches rows that need parsing."""
        query = f"""
            SELECT cik, submission_num, accession_clean, path 
            FROM `{self.project}.{self.dataset}.{table_name}`
            WHERE status = 'PENDING'
            LIMIT {limit}
        """
        return self.client.query(query).to_dataframe()

    def merge_status_updates(self, target_table, staging_table):
        """
        Uses a MERGE statement to update the status of many rows at once.
        This is faster and more reliable than a long 'IN' clause.
        """
        merge_query = f"""
        MERGE `{self.project}.{self.dataset}.{target_table}` T
        USING `{self.project}.{self.dataset}.{staging_table}` S
        ON T.submission_num = S.submission_num
            and CAST(T.cik AS INT64) = CAST(S.cik AS INT64)
        WHEN MATCHED THEN
          UPDATE SET 
            T.status = S.status, 
            T.parsed_at = S.parsed_at,
            T.error_msg = S.error_msg
        """
        self.client.query(merge_query).result()
        print(f"Successfully merged updates from {staging_table} to {target_table}.")