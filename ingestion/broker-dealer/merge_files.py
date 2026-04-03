import os
import numpy as np
import pandas as pd
from datetime import date
from utils import load_data
from utils import get_previous_month
from utils import get_later_month
from utils import find_oldest_file
from utils import get_file_date
from download_bd_file import download_file

def compare_df(new_mm, new_yy, filename='./broker_dealer_master_list.csv'):
    if not os.path.exists(filename):
        print(f'Master file {filename} not found. Creating new master file.')
    master_df = pd.read_csv(filename, dtype={'CIK': str, 'CRD': str})
    latest_master_date = master_df['last_observed_month'].max()
    latest_master_month = latest_master_date.split('_')[1]
    latest_master_year = latest_master_date.split('_')[0]
    if date(int(new_yy), int(new_mm), 1) <= date(int(latest_master_year), int(latest_master_month), 1):
        print(f'New file {new_mm}/{new_yy} is not newer than the latest master file date {latest_master_date}. No update needed.')
        return master_df
    file_name_template = 'bd{mm}01{yy}.txt'
    new_file = file_name_template.format(mm=new_mm, yy=new_yy)
    new_file_path = os.path.join('./files/', new_file)
    if not os.path.exists(new_file_path):
        download_file(new_mm, new_yy)
    if not os.path.exists(new_file_path):
        print(f'New file {new_file} not found after download attempt. Please check the availability of the file.')
        return master_df
    new_df = load_data(new_file_path)
    
    df_merged = pd.merge(
        new_df, 
        master_df,
        on='CIK', 
        how='outer', 
        suffixes=('', '_prev'),
        indicator=True
    )
    
    for col in df_merged.columns:
        original_name = ''
        if col.endswith('_prev'):
            original_name = col[:-5]  

        if original_name in df_merged.columns:
            df_merged[original_name] = df_merged[original_name].fillna(df_merged[col])
            df_merged = df_merged.drop(columns=[col])

    status_map = {
        'left_only': 'New',
        'right_only': 'Withdrawn',
        'both': 'Active'
    }

    df_merged['status'] = df_merged['_merge'].map(status_map)
    df_merged = df_merged.drop(columns=['na', '_merge'])
    file_month = f'{new_yy}_{new_mm}'
    df_merged.loc[df_merged['status'] == 'New', 'start_month'] = file_month
    df_merged.loc[df_merged['status'] == 'Withdrawn', 'withdrawn_month'] = file_month
    df_merged['last_observed_month'] = file_month
    
    return df_merged

def save_df(df, filepath):
    df.to_csv(filepath, index=False)
    print(f"Absolute path: {os.path.abspath(filepath)}")
    print(f'save to {filepath}')
    return None

def update_monthly(start_month, start_year):
    today = date.today()
    dd = today.strftime("%d")
    mm = today.strftime("%m")
    yy = today.strftime("%y")
    
    latest_mm, latest_yy = get_previous_month(mm, yy)
    master_path = './broker_dealer_master_list.csv'
    if os.path.exists(master_path):
        print(f'Master file {master_path} found. Updating master file.')
        pass
    else:
        print(f'Master file {master_path} not found. Creating new master file.')
        try:
            oldest = find_oldest_file("files/")
            if oldest:
                print(f"The oldest file is: {oldest.name}")
                oldest_df = load_data(oldest)
                oldest_date = get_file_date(oldest)
                oldest_df['status'] = 'Active'
                oldest_df['start_month'] = ''
                oldest_df['withdrawn_month'] = ''
                oldest_df['last_observed_month'] = f'{oldest_date.year}_{oldest_date.month:02d}'
                save_df(oldest_df, master_path)
                print(f'Created master file from {oldest.name}')
        except ValueError as e:
            print(f"Error: {e}")
    master_df = pd.read_csv(master_path, dtype={'CIK': str, 'CRD': str})
    latest_master_date = master_df['last_observed_month'].max()
    latest_master_month = latest_master_date.split('_')[1]
    latest_master_year = latest_master_date.split('_')[0]
    if date(int(start_year), int(start_month), 1) <= date(int(latest_master_year), int(latest_master_month), 1):
        start_month, start_year = get_later_month(latest_master_month, latest_master_year)
    print(f'Starting update from {start_month}/{start_year} to {latest_mm}/{latest_yy}')
    for yy in range(int(start_year), int(latest_yy) + 1):
        for mm in range(1, 13):
            mm_str = f'{mm:02d}'
            yy_str = f'{yy:02d}'
            if (yy_str == latest_yy) and (mm_str > latest_mm):
                break
            if (yy_str == start_year) and (mm_str < start_month):
                continue
            temp_path = f'./files/broker_dealer_master_list_{mm_str}_{yy_str}.csv'
            df = compare_df(mm_str, yy_str, filename=master_path)
            print(df.shape)
            save_df(df, temp_path)
            try:
                os.replace(temp_path, master_path)
                print(f'Updated master file to {master_path}')
            except Exception as e:
                print(f'Error updating master file: {e}')

if __name__ == "__main__":
    update_monthly(start_month='02', start_year='26')
    df = pd.read_csv('./broker_dealer_master_list.csv', dtype={'CIK': str, 'CRD': str})
    new_df = df[df['start_month'].notna()]
    print(new_df)