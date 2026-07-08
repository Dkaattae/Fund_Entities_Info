# Project Guidelines

## Credentials
- The BigQuery API key is available in the environment. Read it directly from the env at runtime.
- Do not write the BigQuery API key (or any credentials) into any file in the repo.

## Tooling
- Preferred ingestion tool: `dlt`.
- Transform tool: `dbt` (project at `transform/sec_filings/`).
