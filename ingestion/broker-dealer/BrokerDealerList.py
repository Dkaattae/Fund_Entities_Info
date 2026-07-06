"""Scrape X-17A-5 (annual report) accountant info for active broker-dealers.

Reads the broker-dealer list from the BigQuery master table (maintained by
merge_files.py), pulls each firm's latest X-17A-5 filing from EDGAR, and
extracts the accountant/auditor block into broker_dealer_info.csv.
"""
import os
import json
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from google.cloud import bigquery


headers = {
    "User-Agent": "HedgeFundNet katechen150621@gmail.com"
}

DATASET_NAME = "broker_dealer"
MASTER_TABLE = "broker_dealer_master"


def load_bd_list_from_bq():
	"""Return the current (non-withdrawn) broker-dealer list from the master table."""
	service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")
	if not service_account_json_str:
		raise ValueError("Secret not found! Check your Codespace environment variables.")
	gcp_credentials = json.loads(service_account_json_str)
	project_id = gcp_credentials.get("project_id")
	client = bigquery.Client.from_service_account_info(gcp_credentials)
	query = f"""
		SELECT cik, name, film_number, address, address2, city, state, zip
		FROM `{project_id}.{DATASET_NAME}.{MASTER_TABLE}`
		WHERE status != 'Withdrawn'
	"""
	return client.query(query).to_dataframe()


def get_accession_number(CIK):
	cik_padded = str(CIK).zfill(10)
	accession_url = f'https://data.sec.gov/submissions/CIK{cik_padded}.json'
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
	"""Extract fiscal-year-end from the submission info table. Returns None
	instead of raising when the filing doesn't follow the usual structure."""
	if table is None:
		return None
	label = table.find("td", class_="label", string="and Ending")
	if label is None:
		return None
	sibling = label.find_next_sibling("td")
	if sibling is None or sibling.div is None:
		return None
	return sibling.div.text.strip()


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
		form_info_dict['Fiscal_Year'] = get_fiscal_year(sub_table)
		form_info_dict['Acc_No'] = acc
		form_info_dict['CIK'] = CIK
		return form_info_dict
	else:
		# print(f"Failed to access: {response.status_code}, url: {url}")
		return None


def main():
	bd_df = load_bd_list_from_bq()
	print(f"Loaded {len(bd_df)} active broker-dealers from master table")

	form_info_list = []
	for CIK in bd_df['cik'].to_list():
		try:
			accession_dict = get_accession_number(CIK)
			if accession_dict:
				# if filed in xml
				if accession_dict['file_format'] == 'xml':
					form_info_dict = get_form_info(accession_dict['accessionNumber'], CIK)
					if form_info_dict:
						form_info_dict['file_format'] = 'xml'
						form_info_dict['Last_Filing_Date'] = accession_dict['filingDate']
					else:
						form_info_dict = {'file_format': 'xml_unreadable', 'CIK': CIK}
				else:
					form_info_dict = {'file_format': 'paper', 'CIK': CIK}
			else:
				form_info_dict = {'file_format': 'not_submitted', 'CIK': CIK}
		except Exception as e:
			# One malformed filing must not kill the whole multi-hour run.
			print(f"Error processing CIK {CIK}: {e}")
			form_info_dict = {'file_format': 'error', 'CIK': CIK, 'error_msg': str(e)}

		form_info_list.append(form_info_dict)
		time.sleep(0.15)

	form_df = pd.DataFrame(form_info_list)
	bd_df = bd_df.merge(form_df, left_on='cik', right_on='CIK', how='left')
	bd_df = bd_df.drop(columns=['CIK'])
	bd_df.to_csv('broker_dealer_info.csv', index=False)
	print(f"Wrote broker_dealer_info.csv ({len(bd_df)} rows)")


if __name__ == "__main__":
	main()
