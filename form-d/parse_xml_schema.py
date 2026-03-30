import xmltodict
import pandas as pd
import requests


def get_metadata(cik, accession_number):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    headers = {
        "User-Agent": "FormDParser formd@example.com"
    }
    response = requests.get(url, headers=headers).json()
    filings = response.get('filings', {}).get('recent', {})
    sic = response.get('sic', ['N/A'])
    accession_clean = accession_number.replace('-', '')
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

def split_names(val):
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


def parse_formd_submissions(root, cik, accession_number):
    schemaversion = root.get('schemaVersion', 'N/A')
    submission_type = root.get('submissionType', 'N/A')
    testorlive = root.get('testOrLive', 'N/A')
    metadata = get_metadata(cik, accession_number)
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


def parse_issuers(root, cik, accession_number):
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
        df_issuer[new_issuer_previous_names]= df_issuer['issuerPreviousNameList.previousName'].apply(split_names)
    if 'edgarPreviousNameList.previousName' in df_issuer.columns:
        df_issuer[new_edgar_previous_names]= df_issuer['edgarPreviousNameList.previousName'].apply(split_names)
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

def parse_signatures(root, cik, accession_number):
    df_signature = pd.json_normalize(root.get('offeringData', {}).get('signatureBlock', {}).get('signature', []))
    df_signature['accessionnumber'] = accession_number
    df_signature['signature_seq_key'] = df_signature.groupby('accessionnumber').cumcount() + 1
    df_signature.columns = [col.lower() for col in df_signature.columns]
    signature_dict_list = df_signature.to_dict(orient='records')

    return signature_dict_list

def parse_related_persons(root, cik, accession_number):
    related_data = root.get('relatedPersonsList', {}).get('relatedPersonInfo', [])
    df_related_persons = pd.json_normalize(related_data)
    df_related_persons['accessionnumber'] = accession_number
    df_related_persons['relatedperson_seq_key'] = df_related_persons.groupby('accessionnumber').cumcount() + 1
    new_relationship_names = ['relationship_1', 'relationship_2', 'relationship_3']
    if 'relationshipList.relationship' in df_related_persons.columns:
        df_related_persons[new_relationship_names] = df_related_persons['relationshipList.relationship'].apply(split_names)
    col_to_drop = ['relationshipList.relationship']
    df_related_persons = df_related_persons.drop([c for c in col_to_drop if c in df_related_persons.columns], axis=1)

    relationship_name_mapping = {
        'relatedPersonName.firstName': 'firstname',
        'relatedPersonName.lastName': 'lastname',
        'relatedPersonName.middleName': 'middlename',
        'relatedPersonAddress.street1': 'street1',
        'relatedPersonAddress.street2': 'street2',
        'relatedPersonAddress.city': 'city',
        'relatedPersonAddress.stateOrCountry': 'stateorcountry',
        'relatedPersonAddress.stateOrCountryDescription': 'stateorcountrydescription',
        'relatedPersonAddress.zipCode': 'zipcode',
        'relationship_1': 'relationship_1',
        'relationship_2': 'relationship_2',
        'relationship_3': 'relationship_3',
        'relationshipClarification': 'relationshipclarification'
    }
    df_related_persons = df_related_persons.rename(columns=relationship_name_mapping)
    related_person_dict_list = df_related_persons.to_dict(orient='records')

    return related_person_dict_list

def parse_recipients(root, cik, accession_number):
    df_recipients = pd.json_normalize(root.get('offeringData', {}).get('salesCompensationList', {}).get('recipient', []))
    df_recipients['accessionnumber'] = accession_number
    df_recipients['recipient_seq_key'] = df_recipients.groupby('accessionnumber').cumcount() + 1

    recipient_name_mapping = {
        'recipientName': 'recipientname',
        'recipientCRDNumber': 'recipientcrdnumber',
        'recipientBDName': 'recipientbdname',
        'recipientDBCRDNumber': 'recipientdbcrdnumber',
        'recipientAddress.street1': 'street1',
        'recipientAddress.street2': 'street2',
        'recipientAddress.city': 'city',
        'recipientAddress.stateOrCountry': 'stateorcountry',
        'recipientAddress.stateOrCountryDescription': 'stateorcountrydescription',
        'recipientAddress.zipCode': 'zipcode',
        'statesOfSolicitationList.state': 'states_or_value_list',
        'stateOfSolicitationList.description': 'descriptions_list'
    }
    df_recipients = df_recipients.rename(columns=recipient_name_mapping)
    recipient_dict_list = df_recipients.to_dict(orient='records')
    return recipient_dict_list

def parse_offering_data(root, cik, accession_number):
    df_offering_data = pd.json_normalize(root.get('offeringData', {}))
    drop_offering_cols = [c for c in df_offering_data.columns if c.startswith('salesCompensationList') or c.startswith('signatureBlock')    ]
    df_offering_data.drop(drop_offering_cols, axis=1, inplace=True, errors='ignore')
    df_offering_data['accessionnumber'] = accession_number

    offering_name_mapping = {
        'minimumInvestmentAccepted': 'minimuminvestmentaccepted', 
        'industryGroup.industryGroupType': 'industrygrouptype',
        'issuerSize.revenueRange': 'revenuerange', 
        'federalExemptionsExclusions.item': 'federalexemptionsexclusions_items_list',
        'typeOfFiling.newOrAmendment.isAmendment': 'isamendment',
        'typeOfFiling.dateOfFirstSale.value': 'sale_date',
        'durationOfOffering.moreThanOneYear': 'morethanoneyear',
        'typesOfSecuritiesOffered.isOptionToAcquireType': 'isoptiontoacquretype',
        'businessCombinationTransaction.isBusinessCombinationTransaction': 'isbusinesscombinationtrans',
        'businessCombinationTransaction.clarificationOfResponse': 'buscombclarificationofresp',
        'offeringSalesAmounts.totalOfferingAmount': 'totalofferingamount',
        'offeringSalesAmounts.totalAmountSold': 'totalamountsold',
        'offeringSalesAmounts.totalRemaining': 'totalremaining',
        'offeringSalesAmounts.clarificationOfResponse': 'salesamtclarificationofresp',
        'investors.hasNonAccreditedInvestors': 'hasnonaccreditedinvestors',
        'investors.totalNumberAlreadyInvested': 'totalnumberalreadyinvested',
        'salesCommissionsFindersFees.salesCommissions.dollarAmount': 'salescomm_dollaramount',
        'salesCommissionsFindersFees.findersFees.dollarAmount': 'findersfees_dollaramount',
        'salesCommissionsFindersFees.clarificationOfResponse': 'finderfeeclarificationofresp',
        'useOfProceeds.grossProceedsUsed.dollarAmount': 'grossproceedsused_dollaramount',
        'useOfProceeds.clarificationOfResponse': 'grossproceedsused_clarofresp'
        }
    df_offering_data = df_offering_data.rename(columns=offering_name_mapping)
    return df_offering_data



def parse_formd_xml(xml_content, cik, accession_number):
    raw_dict = xmltodict.parse(xml_content, process_namespaces=True)
    
    accession_clean = accession_number.replace('-', '')
    root = raw_dict.get('edgarSubmission', {})
    formd_submission = parse_formd_submissions(root, cik, accession_number)
    issuer_dict = parse_issuers(root, cik, accession_number)
    signature_dict_list = parse_signatures(root, cik, accession_number)
    related_person_dict_list = parse_related_persons(root, cik, accession_number)
    recipient_dict_list = parse_recipients(root, cik, accession_number)
    offering_dict_list = parse_offering_data(root, cik, accession_number)

    formd_data ={
        "formd_submission": formd_submission, 
        "issuer_dict": issuer_dict, 
        "signature_dict_list": signature_dict_list,
        "related_person_dict_list": related_person_dict_list,
        "recipient_dict_list": recipient_dict_list,
        "offering_dict_list": offering_dict_list
    }
    return formd_data


if __name__ == "__main__":
    file_path = 'raw_data.xml'
    try:
        with open(file_path, 'rb') as f:
            xml_content = f.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        exit(1)

    cik = '0001348362'
    accession_number = '0001348362-25-000018'
    formd_data = parse_formd_xml(xml_content, cik, accession_number)
    print(formd_data)

