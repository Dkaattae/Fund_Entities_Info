# Broker Dealer Pipeline

## Current Steps
Download the latest broker-dealer list from the SEC.  
Load the text file into a DataFrame for easy processing.   
Iterate over each broker-dealer CIK:    
    If an XML filing exists, load the structured form data.    
    If no XML filing exists, mark the submission as paper format in the DataFrame.    
Merge the form information into the original broker-dealer DataFrame.    
Export the consolidated data to a CSV file for analysis.    

## Next Step:
Merge the new data into the existing processed CSV (upsert behavior):    
        Existing broker-dealers are updated if necessary.    
New broker-dealers are added, and their XML filings are processed.    
Insert or update the consolidated data into a database for further analysis.    