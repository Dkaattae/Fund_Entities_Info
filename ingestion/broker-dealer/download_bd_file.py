import os
import requests
import pandas
from datetime import date
from utils import get_previous_month


headers = {
    "User-Agent": "BrokerDealerList xchencws@gmail.com" 
}

def download_file(mm, yy, file_folder='./files/'):
    url_str = 'https://www.sec.gov/files/data/broker-dealers/company-information-about-active-broker-dealers/bd{mm}01{yy}.txt'
    filename = 'bd{mm}01{yy}.txt'
    filepath = os.path.join(file_folder, filename.format(mm=mm, yy=yy))
    print(filepath)
    if os.path.exists(filepath):
        print('file exists')
        return None

    response = requests.get(url_str.format(mm=mm, yy=yy), headers=headers)
    print(response.status_code)
    if response.status_code == 200:
        with open(filepath, 'wb') as file:
            file.write(response.content)
        print(f'write file to {filepath}')
    if response.status_code == 404:
        pm, py = get_previous_month(mm, yy)
        p_filepath = os.path.join(file_folder, filename.format(mm=pm, yy=py))
        if os.path.exists(p_filepath):
            print('files up to date')
        else:
            response_previous = requests.get(url_str.format(mm=pm, yy=py), headers=headers)
            filepath_previous = os.path.join(file_folder, filename.format(mm=pm, yy=py))
            if response_previous.status_code == 200:
                with open(filepath_previous, 'wb') as file:
                    file.write(response_previous.content)
            if response_previous.status_code == 404:
                print('check month')


if __name__ == "__main__":
    today = date.today()
    dd = today.strftime("%d")
    mm = today.strftime("%m")
    yy = today.strftime("%y")

    # data will be released after the month has passed
    latest_mm, latest_yy = get_previous_month(mm, yy)
    download_file(latest_mm, latest_yy)
