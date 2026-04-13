import requests
import pandas as pd
import os
import datetime
import re
from pathlib import Path

def load_data(file_path):
	column_headers = ['CIK', 'Name', 'Film_Number', 'Address', 'Address2', 'City', 'State', 'zip', 'na']
	df = pd.read_csv(
		file_path,
		sep='\t',           
		header=None,       
		names=column_headers,
		encoding='utf-16',
		dtype={'CIK': str, 'Film_Number': str}
		)
	return df

def get_previous_month(mm, yy):
    if mm == '01':
        pm = '12'
        py_int = int(yy) - 1
        py = f'{py_int:02d}'
    else: 
        pm_int = int(mm) - 1
        pm = f'{pm_int:02d}'
        py = yy
    return pm, py
def get_later_month(mm, yy):
	if mm == '12':
		lm = '01'
		ly_int = int(yy) + 1
		ly = f'{ly_int:02d}'
	else: 
		lm_int = int(mm) + 1
		lm = f'{lm_int:02d}'
		ly = yy
	return lm, ly

def get_file_date(file_path):
    pattern = r'^bd(\d{2})01(\d{2})\.txt$'
    match = re.search(pattern, file_path.name)
    
    if not match:
        raise ValueError(f"File naming convention error: '{file_path.name}' does not contain YYYY_MM")
    
    month, year = match.groups()

    return datetime.date(int(year), int(month), 1)

def find_oldest_file(directory_path):
    raw_dir = Path(directory_path)
    # Filter for only CSV files
    files = list(raw_dir.glob("*.txt"))
    
    if not files:
        return None

    # Create a list of tuples: (date_object, file_path)
    dated_files = []
    for f in files:
        file_date = get_file_date(f)
        dated_files.append((file_date, f))
    
    # Sort by the date object (the first element in the tuple)
    dated_files.sort(key=lambda x: x[0])
    
    oldest_date, oldest_file = dated_files[0]
    return oldest_file
