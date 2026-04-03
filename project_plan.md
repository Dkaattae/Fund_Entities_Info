
# Ontology
see DomainModel.yml

# raw data ingestion
dlt

# Semantic Layer
dbt model
layer 1: raw data ingested from sec
layer 2: normalization
map service provider name to canonical name and id. 
combine service providers into one table
layer 3: history
based on each entity id, get history of events
layer 4: derived table from history
current status
layer 5: define cohort, policy and business need
like cohort by AUM size, age, type. 

# Knowledge Base
add service provider table to neo4j. 

# Use Case
### dashboard
showing predefind questions like
1, recent formed funds based on form d
2, fund changing service provider alert
3, count of fund forming by time
4, money raised in first round by time
### recommendation
service provider bundle recommendation
### chatbot
generate sql query based on ontology, get the number and use llm to generate complete answer. 
