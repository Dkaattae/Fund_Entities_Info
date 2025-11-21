# Fund Entities


## Broker Dealer List
*FOCUS*.  
file link: 
f"https://www.sec.gov/files/data/broker-dealers/company-information-about-active-broker-dealers/bd{MM}01{YY}.txt".   
convert txt to dataframe.    
use CIK to find accession number,   
and then go into each file by accession number, to get fiscal year and accountant information.   


## Fund
*Data Source: ADV form*.  
website: https://adviserinfo.sec.gov/adv
part 1.  
link: f"https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2025/ADV_Filing_Data_{yyyyMM}01_{yyyyMMdd}.zip"
yyyyMMdd is the last day of the month. 

