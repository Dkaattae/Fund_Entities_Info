import xmltodict
import pandas as pd
import requests

file_path = 'raw_data.xml'
cik = '0001348362'
accession_number = '0001348362-25-000018'
accession_clean = accession_number.replace('-', '')

def get_metadata(cik, accession_clean):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    headers = {
        "User-Agent": "FormDParser formd@example.com"
    }
    response = requests.get(url, headers=headers).json()
    filings = response.get('filings', {}).get('recent', {})
    sic = response.get('sic', ['N/A'])
    for i in range(len(filings.get('accessionNumber', []))):
        if filings['accessionNumber'][i].replace('-', '') == accession_clean:
            return {
                "cik": cik,
                "accession_number": filings['accessionNumber'][i],
                "file_number": filings['fileNumber'][i],
                "filing_date": filings['filingDate'][i],
                "sic_code": sic,
                "report_date": filings['reportDate'][i],
                "form": filings['form'][i]
            }
    return None

def map_year_of_inc(row):
    choice=None
    value=None

    if row.get('yearOfInc.overFiveYears') == 'true':
        choice = "Five Years Ago or More"
    elif row.get('yearOfInc.yetToBeFormed') == 'true':
        choice = "Yet to be formed"
    elif pd.notnull(row.get('yearOfInc.withinLastFiveYears')):
        choice = "Within Last Five Years"
        value = row.get('yearOfInc.withinLastFiveYears')
    return pd.Series([choice, value])

def split_previous_names(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return pd.Series([None, None, None])
    if isinstance(val, dict):
        names_list = [val]
    elif isinstance(val, list):
        names_list = val
    else:
        return pd.Series([None, None, None])
    
    extracted_names = names_list[:3]
    while len(extracted_names) < 3:
        extracted_names.append(None)
    return pd.Series(extracted_names)


def parse_formd_submissions(root):
    schemaversion = root.get('schemaVersion', 'N/A')
    submission_type = root.get('submissionType', 'N/A')
    testorlive = root.get('testOrLive', 'N/A')
    metadata = get_metadata(cik, accession_clean)
    formd_dict = {
        "accessionnumber": accession_number,
        "fiile_num": metadata.get("file_number", "N/A") if metadata else "N/A",
        "filing_date": metadata.get("filing_date", "N/A") if metadata else "N/A",
        "sic_code": metadata.get("sic_code", "N/A") if metadata else "N/A",
        "schemaversion": schemaversion,
        "submission_type": submission_type,
        "test_or_live": testorlive
    }
    return formd_dict


def parse_issuers(root):
    df_issuer = pd.json_normalize(root.get('primaryIssuer', {}))
    df_coissuers = pd.json_normalize(root.get('coIssuerList', {}).get('coIssuerInfo', []))
    df_issuer['is_primaryIssuer_flag']= True
    df_coissuers['is_primaryIssuer_flag']= False
    df_issuer = pd.concat([df_issuer, df_coissuers], ignore_index=True)
    df_issuer['accessionnumber'] = accession_number
    df_issuer[['yearofinc_choice', 'yearofinc_value']] = df_issuer.apply(map_year_of_inc, axis=1)
    df_issuer['issuer_seq_key'] = df_issuer.groupby('accessionnumber').cumcount() + 1
    new_issuer_previous_names = ['issuer_previousname_1', 'issuer_previousname_2', 'issuer_previousname_3']
    new_edgar_previous_names = ['edgar_previousname_1', 'edgar_previousname_2', 'edgar_previousname_3']
    if 'issuerPreviousNameList.previousName' in df_issuer.columns:
        df_issuer[new_issuer_previous_names]= df_issuer['issuerPreviousNameList.previousName'].apply(split_previous_names)
    if 'edgarPreviousNameList.previousName' in df_issuer.columns:
        df_issuer[new_edgar_previous_names]= df_issuer['edgarPreviousNameList.previousName'].apply(split_previous_names)
    col_to_drop = ['edgarPreviousNameList.previousName', 'issuerPreviousNameList.previousName', 
        'yearOfInc.overFiveYears', 'yearOfInc.yetToBeFormed', 'yearOfInc.withinLastFiveYears']
    df_issuer = df_issuer.drop([c for c in col_to_drop if c in df_issuer.columns], axis=1)

    issuer_name_mapping = {
        'entityName': 'entityname',
        'issuerPhoneNumber': 'issuerphonenumber',
        'jurisdictionOfInc': 'jurisdictionofinc',
        'entityType': 'entitytype',
        'issuerAddress.street1': 'street1',
        'issuerAddress.street2': 'street2',
        'issuerAddress.city': 'city',
        'issuerAddress.stateOrCountry': 'stateorcountry',
        'issuerAddress.zipCode': 'zipcode',
        'issuerAddress.stateOrCountryDescription': 'stateorcountrydescription',
        'is_primaryIssuer_flag': 'is_primaryissuer_flag',
        'yearofinc_choice': 'yearofinc_timespan_choice',
        'yearofinc_value': 'yearofinc_value_entered'
    }
    df_issuer = df_issuer.rename(columns=issuer_name_mapping)
    issuer_dict_list = df_issuer.to_dict(orient='records')
    return issuer_dict_list

def parse_signatures(root):
    df_signature = pd.json_normalize(root.get('offeringData', {}).get('signatureBlock', {}).get('signature', []))
    df_signature['accessionnumber'] = accession_number
    df_signature['signature_seq_key'] = df_signature.groupby('accessionnumber').cumcount() + 1
    df_signature.columns = [col.lower() for col in df_signature.columns]
    signature_dict_list = df_signature.to_dict(orient='records')

    return signature_dict_list

try:
     with open(file_path, 'rb') as f:
        raw_dict = xmltodict.parse(f, process_namespaces=True)
except FileNotFoundError:
    print(f"File not found: {file_path}")
    exit(1)

root = raw_dict.get('edgarSubmission', {})
# formd_submission = parse_formd_submissions(root)
# issuer_dict = parse_issuers(root)
# signature_dict_list = parse_signatures(root)


df_related_persons = pd.json_normalize(root.get('relatedPersonList', {}).get('relatedPersonInfo', []))
df_offering = pd.json_normalize(root.get('offeringData', {}))


# print(len(df_offering))