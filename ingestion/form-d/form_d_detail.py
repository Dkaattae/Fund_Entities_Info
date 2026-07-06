import os
import json
import traceback
import pandas as pd
import time
from datetime import datetime, timezone
import dlt
from bq_client import BigQueryHandler
from prefect import flow, task
from parse_xml_schema import parse_formd_xml, parse_formd, get_xml_url

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")
dataset = "formd_filings_crawler"


def form_d_resource(pending_df, parsed_ids, failed_ids):
    for idx, row in pending_df.iterrows():
        try:
            xml_url = get_xml_url(row['cik'], row['accession_clean'])
            xml_content, status_code = parse_formd(xml_url)
            if status_code == 200 and xml_content:
                print('parsing ', row['cik'], row['submission_num'])
                formd_data = parse_formd_xml(xml_content, row['cik'], row['submission_num'])
                yield formd_data
                parsed_ids.append({
                    "submission_num": row['submission_num'],
                    "cik": row['cik'],
                    "status": "PARSED",
                    "parsed_at": datetime.now(timezone.utc),
                    "error_msg": None
                })
            if status_code != 200:
                failed_ids.append({
                    "submission_num": row['submission_num'],
                    "cik": row['cik'],
                    "status": "FAILED",
                    "parsed_at": datetime.now(timezone.utc),
                    "error_msg": f"HTTP {status_code}"
                })
        except Exception as e:
            print(f"Error parsing {row['submission_num']}: {e}")
            traceback.print_exc()
            failed_ids.append({
                "submission_num": row['submission_num'],
                "cik": row['cik'],
                "status": "FAILED",
                "parsed_at": datetime.now(timezone.utc),
                "error_msg": str(e)})
        time.sleep(0.2)
    print("Completed parsing batch of Form D submissions.")


@task(name="Fetch Pending Submissions")
def fetch_pending_submissions(batch_limit):
    bq = BigQueryHandler(project_id, dataset)
    pending_submissions = bq.get_pending_submissions(limit=batch_limit)
    if pending_submissions.empty:
        print("No pending submissions to parse.")
    return pending_submissions

@task(name="Parse Batch of Submissions")
def run_daily_parser_pipeline(pending_submissions):

    pipeline = dlt.pipeline(
            pipeline_name="sec_formd_parser_pipeline",
            destination="bigquery",
            dataset_name=dataset
        )
    parsed_ids = []
    failed_ids = []

    # Collect all parsed data first, then yield per-table resources
    all_submissions = []
    all_issuers = []
    all_offerings = []
    all_related_persons = []
    all_recipients = []
    all_signatures = []

    for formd_data in form_d_resource(pending_submissions, parsed_ids, failed_ids):
        all_submissions.append(formd_data["formd_submission"])
        all_issuers.extend(formd_data["issuer_dict"])
        all_offerings.extend(formd_data["offering_dict_list"])
        all_related_persons.extend(formd_data["related_person_dict_list"])
        all_recipients.extend(formd_data["recipient_dict_list"])
        all_signatures.extend(formd_data["signature_dict_list"])

    if not all_submissions:
        print("No data to load.")
        return parsed_ids, failed_ids

    try:
        resources = [
            dlt.resource(
                all_submissions,
                name="form_d_submission",
                primary_key=["accessionnumber"],
                write_disposition="merge",
                max_table_nesting=0),
            dlt.resource(
                all_issuers,
                name="issuer",
                primary_key=["accessionnumber", "issuer_seq_key"],
                write_disposition="merge",
                max_table_nesting=0),
            dlt.resource(
                all_offerings,
                name="offering",
                primary_key=["accessionnumber"],
                write_disposition="merge",
                max_table_nesting=0),
            dlt.resource(
                all_related_persons,
                name="related_persons",
                primary_key=["accessionnumber", "relatedperson_seq_key"],
                write_disposition="merge",
                max_table_nesting=0) if all_related_persons else None,
            dlt.resource(
                all_recipients,
                name="recipients",
                primary_key=["accessionnumber", "recipient_seq_key"],
                write_disposition="merge",
                max_table_nesting=0) if all_recipients else None,
            dlt.resource(
                all_signatures,
                name="signatures",
                primary_key=["accessionnumber", "signature_seq_key"],
                write_disposition="merge",
                max_table_nesting=0) if all_signatures else None,
        ]
        resources = [r for r in resources if r is not None]

        load_info = pipeline.run(
            resources,
            credentials=gcp_credentials
        )
        print(load_info)
        print(f"Parsed {len(parsed_ids)} submissions successfully, {len(failed_ids)} failed.")

    except Exception as e:
        print(f"Error during pipeline execution: {e}")
        traceback.print_exc()
        # Do NOT return parsed_ids here: the load failed, so marking these
        # rows PARSED would silently drop them. Leave them PENDING and let
        # the task retry / next run pick them up.
        raise
    return parsed_ids, failed_ids

@task(name="Update Submission Statuses")
def update_submission_statuses(parsed_ids, failed_ids):
    bq = BigQueryHandler(project_id, dataset)
    processed_ids = pd.DataFrame(parsed_ids + failed_ids, 
                                    columns=[
                                                'cik', 
                                                'submission_num', 
                                                'status', 
                                                'parsed_at', 
                                                'error_msg'
                                            ])  
    staging_table = "stg_processed_ids"
    target_table = "formd_daily_submissions"
    
    pipeline = dlt.pipeline(
            pipeline_name="staging_processed_ids",
            destination="bigquery",
            dataset_name=dataset
        )

    pipeline.run(
            processed_ids, 
            table_name=staging_table, 
            write_disposition="replace",
            credentials=gcp_credentials
        )
    
    # Merge the updates into the target table
    bq.merge_status_updates(target_table, staging_table)
    print("Updated submission statuses to 'PARSED' in BigQuery.")


@flow(name="Daily Form D Parser Flow")
def ingestion_flow(batch_limit=1000, exhaust_all=False):
    while True:
        pending_submissions = fetch_pending_submissions(batch_limit)
        if pending_submissions.empty:
            print("No pending submissions to process. Exiting flow.")
            break
        parsed_ids, failed_ids = run_daily_parser_pipeline(pending_submissions)
        if parsed_ids or failed_ids:
            update_submission_statuses(parsed_ids, failed_ids)
        else:            
            print("No more pending submissions to process.")
        if not exhaust_all:
            break  # Exit after one batch if not exhausting all

if __name__ == "__main__":
    # Exhaust the full pending backlog each run. Normal daily volume is a
    # few hundred filings; anything larger means we're catching up a gap.
    ingestion_flow(batch_limit=500, exhaust_all=True)
