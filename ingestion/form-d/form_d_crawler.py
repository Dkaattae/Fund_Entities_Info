import os
import json
import io
import pandas as pd
import requests
import time
import dlt

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

if not service_account_json_str:
    raise ValueError("Secret not found! Check your Codespace environment variables.")

gcp_credentials = json.loads(service_account_json_str)
project_id = gcp_credentials.get("project_id")


headers = {
    "User-Agent": "KateChen xchencws@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
    }


def formd_by_date(start_date, end_date):
    business_days = pd.bdate_range(start=start_date, end=end_date, inclusive='left')
    formd_df_list = []
    url_template = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/master.{date}.idx"
    for date in business_days:
        date_str = date.strftime("%Y%m%d")
        url = url_template.format(year=year, quarter=quarter, date=date_str)
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # Skip the first 10 header rows of the .idx file
            data = response.text.split('--------------------------------------------------------------------------------')[-1]
            
            # Load into DataFrame
            df = pd.read_csv(io.StringIO(data), sep='|', names=['CIK', 'Name', 'Form', 'Date', 'Path'])
            
            # 3. Filter for D and D/A
            target_forms = ['D', 'D/A']
            new_leads = df[df['Form'].str.strip().str.upper().isin(target_forms)]
            
            new_leads_list = new_leads.to_dict('records')
            
            formd_df_list.append(new_leads_list)
            
            time.sleep(0.1)
        else:
            print(f"Failed to retrieve data for {date_str}: {response.status_code}")
        formd_df = pd.DataFrame([item for sublist in formd_df_list for item in sublist])

    return formd_df

def formd_by_quarter(year, quarter):
    month = quarter * 3 - 2
    start_date = f"{year}-{month}-01"
    if quarter == 4:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+3}-01"
    return formd_by_date(start_date, end_date)



def load_formd_data(year, quarter):
    pipeline = dlt.pipeline(
        pipeline_name="sec_formd_pipeline",
        destination="bigquery",
        dataset_name="formd_filings_crawler"
    )

    formd_df = formd_by_quarter(year, quarter)
    formd_df['status'] = 'PENDING'
    formd_df['parsed_at'] = pd.NaT
    formd_df['error_msg'] = None
    formd_df['submission_num'] = formd_df['Path'].apply(lambda x: x.split('/')[-1].replace('.txt', ''))
    formd_df['accession_clean'] = formd_df['submission_num'].str.replace('-', '')   

    load_info = pipeline.run(
        formd_df,
        table_name="formd_daily_submissions",
        primary_key=["CIK", "Path"],
        write_disposition="merge",
        credentials=gcp_credentials
    )
    
    print(load_info)


if __name__ == "__main__":
    quarter = 1
    year = 2026
    load_formd_data(year, quarter)