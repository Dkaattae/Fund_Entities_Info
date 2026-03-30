import os
import json
import pandas as pd
import requests
import time
from datetime import datetime, timezone
from lxml import etree
import dlt
from bq_client import BigQueryHandler
from dlt.destinations import filesystem
from prefect import flow, task

headers = {
    "User-Agent": "BrokerDealerList xchencws@gmail.com" 
}

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")
dataset = "formd_filings_crawler"
bucket_url = os.getenv("BUCKET_URL")
staging_destination = filesystem(bucket_url=bucket_url, credentials=gcp_credentials)


def get_xml_url(cik, accession_clean):
    base_url = "https://www.sec.gov/Archives/"
    
    # Path is: edgar/data/{CIK}/{CleanAccession}/primary_doc.xml
    xml_url = f"{base_url}edgar/data/{cik}/{accession_clean}/primary_doc.xml"
    
    return xml_url

def parse_formd(xml_url):
    response = requests.get(xml_url, headers=headers)
    if response.status_code == 200:
        return response.content, response.status_code
    else:
        print(f"Failed to access: {response.status_code}, url: {xml_url}")
        return None, response.status_code

def extract_form_d_leads(xml_content):
    tree = etree.fromstring(xml_content)
    
    # Get Firm-wide Contact Info
    date_filed = tree.xpath('//signatureDate/text()')[0]
    firm_name = tree.xpath('//primaryIssuer/entityName/text()')[0]
    cik = tree.xpath('//primaryIssuer/cik/text()')[0]
    date_val = tree.xpath('//dateOfFirstSale/value/text()')
    date_first_sale = date_val[0] if date_val else None
    investment_type = tree.xpath(".//investmentFundInfo/investmentFundType/text()")
    investment_type = investment_type[0] if investment_type else "N/A"
    is_equity = tree.xpath(".//typesOfSecuritiesOffered/isEquityType/text()")
    is_equity = is_equity[0] if is_equity else "false"
    phone = tree.xpath('//primaryIssuer/issuerPhoneNumber/text()')[0]
    money = tree.xpath('//offeringSalesAmounts/totalAmountSold/text()')[0]
    remaining_amt = tree.xpath("//offeringSalesAmounts/totalRemaining/text()")[0]

    # Get the "Related Persons" (Owners/Decision Makers)
    # This often returns a list if there are multiple owners
    owners = []
    for person in tree.xpath('//relatedPersonInfo'):
        first = person.xpath('.//firstName/text()')[0]
        last = person.xpath('.//lastName/text()')[0]
        title = person.xpath('.//relationship/text()')[0]
        owners.append({"firstName": first, "lastName": last, "role": title})
        
    return {
        "firm": firm_name,
        "cik": cik,
        "date_filed": date_filed,
        "phone": phone,
        "owners": owners,
        "date_first_sale": date_first_sale,
        "investment_type": investment_type,
        "is_equity": is_equity,
        "money_raised": money,
        "remaining_amount": remaining_amt
    }

@dlt.resource(
    table_name="formd_parsed_leads", 
    write_disposition="merge", 
    primary_key=["cik", "submission_num"])
def form_d_resource(pending_df, parsed_ids, failed_ids):
    for idx, row in pending_df.iterrows():
        try:
            xml_url = get_xml_url(row['cik'], row['accession_clean'])
            xml_content, status_code = parse_formd(xml_url)
            if status_code == 200 and xml_content:
                lead_info = extract_form_d_leads(xml_content)
                lead_info['submission_num'] = row['submission_num']
                lead_info['cik'] = row['cik']
                yield lead_info
                parsed_ids.append({
                    "submission_num": row['submission_num'], 
                    "cik": row['cik'],
                    "status": "PARSED",
                    "parsed_at": datetime.now(timezone.utc),
                    "error_msg": None
                }),
            if status_code != 200:
                failed_ids.append({
                    "submission_num": row['submission_num'], 
                    "cik": row['cik'], 
                    "status": "FAILED",
                    "parsed_at": datetime.now(timezone.utc),
                    "error_msg": f"HTTP {status_code}"
                })
        except Exception as e:
            failed_ids.append({
                "submission_num": row['submission_num'], 
                "cik": row['cik'], 
                "status": "FAILED",
                "parsed_at": datetime.now(timezone.utc),
                "error_msg": str(e)})
        time.sleep(0.2)  # Be polite to the SEC servers
    print("Completed parsing batch of Form D submissions.")


@task(name="Fetch Pending Submissions")
def fetch_pending_submissions(batch_limit):
    bq = BigQueryHandler(project_id, dataset)
    pending_submissions = bq.get_pending_submissions(limit=batch_limit)
    if pending_submissions.empty:
        print("No pending submissions to parse.")
    return pending_submissions

@task(name="Parse Batch of Submissions", retries=3)
def run_daily_parser_pipeline(pending_submissions):

    pipeline = dlt.pipeline(
            pipeline_name="sec_formd_parser_pipeline",
            destination="bigquery",
            dataset_name=dataset
        )
    parsed_ids = []
    failed_ids = []
    try:
        load_info = pipeline.run(
            form_d_resource(pending_submissions, parsed_ids, failed_ids),
            table_name = "formd_parsed_leads",
            primary_key = ["cik", "submission_num"],
            write_disposition = "merge",
            credentials=gcp_credentials
            )
        print(load_info)
        print(f"Parsed {len(parsed_ids)} submissions successfully, {len(failed_ids)} failed.")

    except Exception as e:
        print(f"Error during pipeline execution: {e}")
    finally:
        print("Closing pipeline resources.")
    return parsed_ids, failed_ids

@task(name="Update Submission Statuses")
def update_submission_statuses(parsed_ids, failed_ids):
    bq = BigQueryHandler(project_id, dataset)
    processed_ids = pd.DataFrame(parsed_ids + failed_ids, 
                                    columns=[
                                                'cik', 
                                                'submission_number', 
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
    ingestion_flow(batch_limit=5000)
