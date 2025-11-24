import pandas as pd
import requests
import time
from bs4 import BeautifulSoup
from utils import load_data


headers = {
    "User-Agent": "BrokerDealerList xchencws@gmail.com" 
}

def get_accession_number(CIK):
	accession_url = f'https://data.sec.gov/submissions/CIK{CIK}.json'
	try:
		response = requests.get(accession_url, headers=headers)
	
		# Check if request was successful
		if response.status_code == 200:
			data = response.json()
			recent_filings = data['filings']['recent']
            
			df = pd.DataFrame(recent_filings)
			target_df = df[['accessionNumber', 'filingDate', 'form', 'primaryDocument']]
			target_df = target_df[target_df['primaryDocument'] == 'xslX-17A-5_X01/primary_doc.xml']
			if not target_df.empty:
				target_record = target_df.sort_values("filingDate", ascending=False).iloc[0]
				target_dict = target_record.to_dict()
				target_dict['file_format'] = 'xml'
				return target_dict
			else:
				return {'file_format': 'paper'}
		else:
			print(f"Error for {CIK}: {response.status_code}")
			return None
	except Exception as e:
		print(f"Failed to pull {CIK}: {e}")
		return None

def get_accountant_info(table):
	label_map = {
		"Name": "Acct_Name",  # Starts with Name...
		"Address 1": "Acct_Address",
		"City": "Acct_City",
		"State/Country": "Acct_State",
		"Mailing Zip/ Postal Code": "Acct_Zip",
		"Check One": "Check One"
	}

	data = {}

	rows = table.find_all('tr')
	for row in rows:
		label_cell = row.find('td', class_='label')
		if not label_cell: 
			continue

		raw_label = label_cell.get_text(strip=True)

		clean_col_name = None
		for k, v in label_map.items():
			if raw_label.startswith(k):
				clean_col_name = v
				break
        
		if clean_col_name:
			val_cell = label_cell.find_next_sibling('td')

			fake_box = val_cell.find('div', class_='fakeBox')
            
			if fake_box:
				data[clean_col_name] = fake_box.get_text(strip=True)
            
			else:
				checked = val_cell.find('img', alt="Radio button checked")

				if checked:
					data[clean_col_name] = checked.next_element.strip()

	return data

def get_fiscal_year(table):
	label = table.find("td", class_="label", string="and Ending")
	value = label.find_next_sibling("td").div.text.strip()
	return value


def get_form_info(acc, CIK):
	base_url = "https://www.sec.gov/Archives/edgar/data"
	acc_no_dashes = acc.replace('-', '') 
	filename = "xslX-17A-5_X01/primary_doc.xml"
	cik = int(CIK)
	url = f"{base_url}/{cik}/{acc_no_dashes}/{filename}"
	
	response = requests.get(url, headers=headers)

	if response.status_code == 200:
		soup = BeautifulSoup(response.content, 'xml')

		acct_table = soup.find(id='accountantIdentification')
		sub_table = soup.find(id='submissionInformation')
		form_info_dict = {}
		if acct_table:
			form_info_dict = get_accountant_info(acct_table)
		fiscal_year = get_fiscal_year(sub_table)
		form_info_dict['Fiscal_Year'] = fiscal_year
		form_info_dict['Acc_No'] = acc
		form_info_dict['CIK'] = CIK
		return form_info_dict
	else:
		# print(f"Failed to access: {response.status_code}, url: {url}")
		return None


bd_df = load_data('./files/bd100125.txt')
cik_list = bd_df['CIK'].to_list()
accession_dict = []
form_info_list = []

for CIK in cik_list:
	accession_dict = get_accession_number(CIK) 
	if accession_dict:
		# if filed in xml
		if accession_dict['file_format'] == 'xml':
			acc = accession_dict['accessionNumber']
			last_filing = accession_dict['filingDate']
			form_info_dict = get_form_info(acc, CIK)
			if form_info_dict:
				form_info_dict['file_format'] = 'xml'
			else: print(accession_dict)
		else:
			form_info_dict = {'file_format': 'paper', 'CIK': CIK}
	else: 
		form_info_dict = {'file_format': 'not_submitted', 'CIK': CIK}
	form_info_list.append(form_info_dict)

	time.sleep(0.15)

bd_df = bd_df.drop('na', axis=1)
form_info_list = [d for d in form_info_list if d != None]

form_df = pd.DataFrame(form_info_list)

bd_df = bd_df.merge(form_df, on='CIK', how='left')

bd_df.to_csv('broker_dealer_info.csv')