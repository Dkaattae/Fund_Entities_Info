import os
import pandas as pd
from utils import load_data
from utils import get_previous_month
from download_bd_file import download_file

def compare_df(latest_mm, latest_yy, filename='./files/bd{mm}01{yy}.txt'):
    current_file = filename.format(mm=latest_mm, yy=latest_yy)
    
    if not os.path.exists(current_file):
        download_file(latest_mm, latest_yy)
    latest_df = load_data(current_file)
    
    pm, py = get_previous_month(latest_mm, latest_yy)
    previous_file = filename.format(mm=pm, yy=py)
    
    if not os.path.exists(previous_file):
        download_file(pm, py)
        
    previous_df = load_data(previous_file)
    print(previous_df.shape)
    df_merged = pd.merge(
        latest_df, 
        previous_df,
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
    return df_merged

def save_df(df, filepath):
    df.to_csv(filepath, index=False)
    print(f'save to {filepath}')
    return None

if __name__ == "__main__":
    latest_mm = '10'
    latest_yy = '25'
    df = compare_df(latest_mm, latest_yy)
    save_df(df, 'broker_dealer_list.csv')
