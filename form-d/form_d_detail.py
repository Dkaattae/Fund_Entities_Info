import pandas as pd
import requests
import time
from utils import load_data
from lxml import etree

headers = {
    "User-Agent": "BrokerDealerList xchencws@gmail.com" 
}

def get_xml_url(crawler_idx_path):
    base_url = "https://www.sec.gov/Archives/"
    
    # 1. Split the path to isolate the accession number (the last part)
    parts = crawler_idx_path.split('/')
    filename = parts[-1]  # '0001041588-25-000005.txt'
    accession_with_dashes = filename.replace('.txt', '')
    
    # 2. Strip the dashes
    accession_clean = accession_with_dashes.replace('-', '')
    
    # 3. Rebuild the folder path
    # Path is: edgar/data/{CIK}/{CleanAccession}/primary_doc.xml
    cik = parts[2]
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
    
    # 1. Get Firm-wide Contact Info
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

    # 2. Get the "Related Persons" (Owners/Decision Makers)
    # This often returns a list if there are multiple owners
    owners = []
    for person in tree.xpath('//relatedPersonInfo'):
        first = person.xpath('.//firstName/text()')[0]
        last = person.xpath('.//lastName/text()')[0]
        title = person.xpath('.//relationship/text()')[0]
        owners.append({"name": f"{first} {last}", "role": title, "cik": cik})
        
    return {
        "firm": firm_name,
        "cik": cik,
        "phone": phone,
        "leads": owners,
        "title": title,
        "money_raised": money
    }

if __name__ == "__main__":
    formd_df = pd.read_csv('formD_2025_Q4.csv')
    formd_df['xml_url'] = formd_df['Path'].apply(get_xml_url)
    
    leads_data = []
    for idx, row in formd_df.iterrows():
        xml_content = parse_formd(row['xml_url'])
        if xml_content:
            lead_info = extract_form_d_leads(xml_content)
            leads_data.append(lead_info)
        time.sleep(0.1)  # Be polite to the SEC servers
    
    leads_df = pd.DataFrame(leads_data)
    print(leads_df.head())
    leads_df.to_csv('formD_leads_2025_Q4.csv', index=False)