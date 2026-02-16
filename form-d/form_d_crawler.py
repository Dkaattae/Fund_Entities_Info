import io
import pandas as pd
import requests
import time
from bs4 import BeautifulSoup
from utils import load_data

headers = {
    "User-Agent": "KateChen xchencws@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
    }


url_template = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/master.{date}.idx"

formd_df_list = []
quarter = 4
year = 2025

def form_bd_by_quarter(year, quarter):
    month = quarter * 3 - 2
    start_date = f"{year}-{month}-01"
    if quarter == 4:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+3}-01"
    business_days = pd.bdate_range(start=start_date, end=end_date, inclusive='left')
    for date in business_days:
        date_str = date.strftime("%Y%m%d")
        url = url_template.format(year=year, quarter=quarter, date=date_str)
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # Skip the first 10 header rows of the .idx file
            data = response.text.split('--------------------------------------------------------------------------------')[-1]
            
            # Load into DataFrame
            df = pd.read_csv(io.StringIO(data), sep='|', names=['CIK', 'Name', 'Form', 'Date', 'Path'])
            
            # 3. Filter for BD and BD/A
            new_leads = df[df['Form'].str.strip().str.upper() == 'D']
            
            new_leads_list = new_leads.to_dict('records')
            
            formd_df_list.append(new_leads_list)
            
            time.sleep(0.1)
        else:
            print(f"Failed to retrieve data for {date_str}: {response.status_code}")
        formd_df = pd.DataFrame([item for sublist in formd_df_list for item in sublist])

    return formd_df

if __name__ == "__main__":
    formd_df = form_bd_by_quarter(year, quarter)
    print(formd_df.shape)
    formd_df.to_csv(f'formD_{year}_Q{quarter}.csv', index=False)