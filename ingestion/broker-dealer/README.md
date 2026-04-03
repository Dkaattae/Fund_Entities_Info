# Broker Dealer Pipeline

## Current Steps
Download the latest broker-dealer list from the SEC.  
Load the text file into a DataFrame for easy processing.   
Iterate over each broker-dealer CIK:    
    If an XML filing exists, load the structured form data.    
    If no XML filing exists, mark the submission as paper format in the DataFrame.    
Merge the form information into the original broker-dealer DataFrame.    
Export the consolidated data to a CSV file for analysis.    

Merge the new data into the existing processed CSV (upsert behavior):    
        Existing broker-dealers are updated if necessary.    
New broker-dealers are added, and their XML filings are processed.    
Insert or update the consolidated data into a database for further analysis.    

## Next Steps 
- **pcaob form2**
- get pcaob id
scrape firm directory
- pull filings
try url: https://pcaobus.org/api/firm/{id}/filings
https://pcaobus.org/oversight/registered-firms/firm-details/{ID}?tab=filings
https://pcaobus.org/oversight/registered-firms/firm-details/{id}
- normalize
match entity name, match crd number

- **(ToS Restriction, cannot scrape in bulk)**
based on current list, get crd number from each row. 
- html
go to url 'https://brokercheck.finra.org/firm/summary/{CRD}'
to get informations:
number of disclosures, approved date, company type, regulatory orgs,
general information: main office location, mailing address, phone, established in, type, fiscal year end.
direct owners and executive officers: [{name, position}]
licenses: state, federal, self regulatory org

- pdf
firm operations: types of business
disclosure event details: report source: regulator, report source: firm