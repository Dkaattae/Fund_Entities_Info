import requests
import pandas as pd
import os
import datetime

def load_data(file_path):
	column_headers = ['CIK', 'Name', 'CRD', 'Address', 'Address2', 'City', 'State', 'zip', 'na']
	df = pd.read_csv(
		file_path,
		sep='\t',           
		header=None,       
		names=column_headers,
		encoding='utf-16',
		dtype={'CIK': str, 'CRD': str}
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