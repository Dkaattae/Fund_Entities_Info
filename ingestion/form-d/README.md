# Form D Pipeline

SEC EDGAR Form D filings data pipeline. Ingests Form D data into BigQuery via two paths: quarterly historical backfill and daily incremental updates.

## Data Source

- **SEC EDGAR Form D structured data sets** - quarterly bulk TSV archives
- **SEC EDGAR daily index files** - daily master.idx for new filings
- **SEC EDGAR XML filings** - individual Form D XML for detail parsing

## Architecture

### Historical Backfill (quarterly)

Downloads quarterly bulk ZIP archives from SEC (`{year}q{quarter}_d.zip`), which contain pre-parsed TSV files for each table. Loads directly into BigQuery dataset `form_d_filings` via dlt.

```
SEC bulk ZIP -> extract TSV -> dlt -> BigQuery (form_d_filings)
```

Tables: `FormDSubmission`, `Issuer`, `Offering`, `RelatedPersons`, `Recipients`, `Signatures`

### Daily Update (incremental)

1. **Crawl**: Download daily index files from EDGAR, filter for Form D/D-A filings, load into a tracking table with status `PENDING`.
2. **Parse**: For each pending record, fetch the XML from EDGAR, parse it into the same schema as historical data, and load into BigQuery.
3. **Status update**: Mark processed records as `PARSED` or `FAILED` in the tracking table.

```
EDGAR daily index -> filter D/D-A -> tracking table (PENDING)
    -> fetch XML per filing -> parse XML -> BigQuery (formd_filings_crawler)
    -> update tracking table (PARSED/FAILED)
```

### Schema Alignment

Daily parsed XML data uses the same column names (lowercased) as the historical backfill TSV tables, so both can be queried consistently in BigQuery. After a quarter ends, run the historical backfill for that quarter and clean up the daily table.

## Files

| File | Description |
|---|---|
| `backfill.py` | Quarterly historical backfill from SEC bulk ZIP archives |
| `form_d_crawler.py` | Daily index crawler - finds new Form D filings |
| `form_d_detail.py` | Daily parser pipeline - fetches and parses individual filings (Prefect flow) |
| `parse_xml_schema.py` | XML parsing and column mapping for Form D filings |
| `bq_client.py` | BigQuery helper for pending submission queries and status merges |
| `local_backlog.py` | Local backlog processing utility |
| `wipe_dlt.py` | Utility to reset dlt pipeline state |

## BigQuery Datasets

- `form_d_filings` - Historical backfill data (quarterly bulk loads)
- `formd_filings_crawler` - Daily incremental data (per-filing XML parsing)

## Tables (per dataset)

| Table | Primary Key | Description |
|---|---|---|
| `FormDSubmission` | `ACCESSIONNUMBER, FILE_NUM` | Filing metadata |
| `Issuer` | `ACCESSIONNUMBER, ISSUER_SEQ_KEY` | Primary issuer and co-issuers |
| `Offering` | `ACCESSIONNUMBER` | Offering details, exemptions, amounts |
| `RelatedPersons` | `ACCESSIONNUMBER, RELATEDPERSON_SEQ_KEY` | Directors, officers, promoters |
| `Recipients` | `ACCESSIONNUMBER, RECIPIENT_SEQ_KEY` | Sales compensation recipients |
| `Signatures` | `ACCESSIONNUMBER, SIGNATURE_SEQ_KEY` | Signature block |

## Usage

```bash
# Historical backfill (e.g., 2025 Q1 onward)
python backfill.py

# Daily crawl - load new filings into tracking table
python form_d_crawler.py

# Daily parse - process pending filings from tracking table
python form_d_detail.py
```

## Environment Variables

- `BIGQUERY_SERVICE_ACCOUNT_JSON` - GCP service account JSON string
- `BUCKET_URL` - GCS bucket URL for dlt staging

## Potential concerns when expanding historical data

Current coverage starts at 2024 Q1. SEC publishes quarterly Form D data sets
back to 2008, so a deeper backfill is possible, but be aware of:

1. **Metadata lookup misses old filings (daily path only).**
   `parse_xml_schema.get_metadata()` reads the SEC submissions API's `recent`
   window (~1,000 most recent filings per CIK). For a prolific filer, an old
   accession number may not be in that window, leaving `filing_date`,
   `file_num`, and `sic_code` blank in the crawler dataset. This does not
   affect the quarterly bulk path — the TSVs carry their own metadata — so
   expand history via `backfill.py`, never by crawling old daily indexes.
2. **Older bulk ZIPs may have different columns.** The Form D structured data
   sets evolved over the years; earlier quarters can miss columns the staging
   models select. dlt will load whatever is present, but check
   `stg_form_d_*` compile against the oldest loaded quarter.
3. **"First raise" marts will reinterpret history.** `form_d_first_raise`,
   `form_d_new_funds_by_quarter`, and `newly_emerging_funds` treat the
   earliest filing *in the loaded window* as the first. Loading older data
   will (correctly) reclassify funds that looked new in 2024 — expect counts
   for existing quarters to change.
4. **Amendments referencing pre-window originals.** D/A filings whose
   original accession predates the window currently dangle; expanding
   history resolves some of those chains and changes amendment-aware logic.

## Status

- Backfill: working, quarterly data loaded in BQ from 2024 Q1
- Daily crawler: working (resumes from last covered date across bulk + tracking)
- Daily XML parser: working (`batch_limit=500`, exhausts the pending backlog each run)
