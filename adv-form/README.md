# SEC Form ADV Data Pipeline

A robust data engineering pipeline designed to ingest, normalize, and store SEC Form ADV filings (Investment Adviser Public Disclosure data) into a relational PostgreSQL database.

## 📖 Project Overview

The SEC provides Form ADV data in bulk CSV format. However, given the volume of data and the relational nature of the filings (advisers to funds to auditors), flat-file local storage is insufficient for complex analysis.

This project automates the ETL process to migrate this data into a cloud-hosted PostgreSQL instance (Supabase), enabling SQL-based querying of the investment landscape.

## 🛠 Tech Stack

* **Orchestration:** [Prefect](https://www.prefect.io/) (Workflow management, scheduling, and observability)
* **Data Loading:** [dlt (Data Load Tool)](https://dlthub.com/) (Schema evolution, normalization, and loading CSVs to SQL)
* **Database:** [Supabase](https://supabase.com/) (Managed PostgreSQL)
* **Source:** SEC Investment Adviser Public Disclosure (IAPD) Bulk Data

## 🏗 Architecture

1.  **Extract:** Prefect task fetches the monthly/quarterly bulk CSV files from the SEC IAPD website.
2.  **Transform/Normalize:** `dlt` parses the raw CSVs, handles type inference, and creates the necessary relational schema.
3.  **Load:** Data is upserted into Supabase.

## 🗄 Data Model

The pipeline transforms the flat CSVs into a normalized star schema suitable for analytics. Key tables include:

| Table | Description | Key Attributes |
| :--- | :--- | :--- |
| **Advisers** | Core entity table (Form ADV Part 1A) | Name, Address, Regulatory Status (RIA vs. ERA), AUM, Total Employees/Partners. |
| **Private_Funds** | Details on funds managed (Schedule D, Sec 7.B) | Fund Name, Gross Assets, Type (Hedge/PE), Domicile. |
| **Broker_Dealers** | Related brokerage entities | Name, CRD Number, Relationship type. |
| **Custodians** | Asset custody information | Name, Location, Amount custodied. |
| **Auditors** | Audit firms servicing the funds | Name, Location, PCAOB Registration status. |

## 🚀 Goals & Usage

The end goal is to enable complex SQL queries to answer questions such as:
* *Which auditors service the most high-AUM Private Equity funds?*
* *What is the distribution of RIAs vs. ERAs in specific geographic regions?*
* *Map relationships between specific custodians and hedge funds.*

## 🏃‍♂️ Getting Started
