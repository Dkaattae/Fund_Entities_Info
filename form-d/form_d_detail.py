import os
import json
import pandas as pd
import requests
import time
from lxml import etree
import dlt
from bq_client import BigQueryHandler


headers = {
    "User-Agent": "BrokerDealerList xchencws@gmail.com" 
}

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")
dataset = "formd_filings"

def format_owners(owner_list):
    if not owner_list:
        return None
    formatted = []
    for d in owner_list:
        fn = d.get('firstName', '')
        ln = d.get('lastName', '')
        name = f"{fn} {ln}".strip()
        role = d.get('role', 'N/A').strip()
        formatted.append(f"{name} ({role})")
    return "; ".join(formatted)

def get_xml_url(cik, accession_clean):
    base_url = "https://www.sec.gov/Archives/"
    
    # Path is: edgar/data/{CIK}/{CleanAccession}/primary_doc.xml
    xml_url = f"{base_url}edgar/data/{cik}/{accession_clean}/primary_doc.xml"
    
    return xml_url

def parse_formd(xml_url):
    response = requests.get(xml_url, headers=headers)
    if response.status_code == 200:
        return response.content
    else:
        print(f"Failed to access: {response.status_code}, url: {xml_url}")
        return None

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
        owners.append({"name": f"{first} {last}", "role": title})
        
    return {
        "firm": firm_name,
        "cik": cik,
        "date_filed": date_filed,
        "phone": phone,
        "owners": format_owners(owners),
        "title": title,
        "date_first_sale": date_first_sale,
        "investment_type": investment_type,
        "is_equity": is_equity,
        "money_raised": money,
        "remaining_amount": remaining_amt
    }

def run_parser_pipeline():
    bq = BigQueryHandler(project_id, dataset)

    while True:
        print("Checking for pending submissions...")
        pending_submissions = bq.get_pending_submissions(limit=1000)
        if pending_submissions.empty:
            print("No pending submissions to parse.")
            break
        
        pending_submissions['xml_url'] = pending_submissions.apply(lambda x: get_xml_url(x['cik'], x['accession_clean']), axis=1)
        leads_data = []
        for idx, row in pending_submissions.iterrows():
            xml_content = parse_formd(row['xml_url'])
            if xml_content:
                lead_info = extract_form_d_leads(xml_content)
                lead_info['submission_num'] = row['submission_num']
                leads_data.append(lead_info)
            time.sleep(0.1)  # Be polite to the SEC servers
        
        leads_df = pd.DataFrame(leads_data)

        try:
            pipeline = dlt.pipeline(
                pipeline_name="sec_formd_parser_pipeline",
                destination="bigquery",
                dataset_name=dataset
            )

            load_info = pipeline.run(
                leads_df,
                table_name = "formd_parsed_leads",
                primary_key = ["cik", "submission_num"],
                write_disposition = "merge",
                loader_file_format="parquet",
                credentials=gcp_credentials
            )
            print(load_info)

            processed_ids = leads_df[['submission_num']]
            pipeline.run(
                processed_ids, 
                table_name="stg_processed_ids", 
                write_disposition="replace",
                credentials=gcp_credentials
            )

            # Trigger the MERGE in BigQuery to flip the status to 'PARSED'
            bq.merge_status_updates("formd_daily_submissions", "stg_processed_ids")
        except Exception as e:
            print(f"Error during pipeline execution: {e}")
            break



if __name__ == "__main__":
    run_parser_pipeline()