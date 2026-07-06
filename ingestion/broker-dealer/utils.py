import pandas as pd

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
