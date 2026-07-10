"""Ingest the PCAOB registered-firms directory (+ inspection reports) into BigQuery.

Purpose: validate the PCAOB numbers advisers self-report for their auditors in
Form ADV (stg_era_auditors.pcaob_number) against the actual PCAOB registry —
the custodian-LEI / prime-broker-BD pattern. See project_plan.md "PCAOB
Ingestion Plan (AUDITOR wiring)".

Sources (both official, measured 2026-07-10):
  registered_firms  The COMPLETE firm directory (~4.1k firms incl. withdrawn/
                    revoked), fetched from the JSON search API behind
                    pcaobus.org/oversight/registration/registered-firms
                    (Hawksearch; ~43 paged requests). A strict superset of the
                    Form AP bulk CSV (issuer-audit firms only, would validate
                    just 52% of reported numbers) and of the inspection
                    datasets — so it is the one validation surface.
                    Withdrawn/revoked firms are kept: a reported number still
                    identifies the firm even after it deregisters (same
                    reasoning as withdrawn broker-dealers in the BD master);
                    registration_status is an attribute, not an identity gate.
  firm_inspections  Firm inspection reports metadata (official CSV download,
                    UTF-16LE), one row per published inspection report.
                    Enrichment evidence for Auditor Watch (cross-checks the
                    self-reported pcaob_inspected flag); not used for identity.

Tables (dataset `pcaob`, write_disposition=replace). Both carry a `load_ts`
column stamped at load time — dlt's pandas/arrow path adds no _dlt_load_id,
so load_ts is the freshness / already-loaded-this-month signal
(orchestration/flows.py pcaob_monthly + sources.yml freshness), the GLEIF
lesson.

Usage:
  python pcaob_ingestion.py     # fetch directory + inspections CSV, load both

Cadence: monthly via the pcaob-monthly flow (see orchestration/flows.py);
safe to re-run ad hoc — each load fully replaces both tables.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import dlt
import pandas as pd
import requests

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")
if not service_account_json_str:
    raise ValueError("BIGQUERY_SERVICE_ACCOUNT_JSON not set.")

gcp_credentials = json.loads(service_account_json_str)

HEADERS = {"User-Agent": "HedgeFundNet katechen150621@gmail.com"}
FILES_DIR = Path(__file__).resolve().parent / "files"

DATASET = "pcaob"

# The registered-firms directory page is a JS app over a Hawksearch index;
# these values come from its data-* attributes (data-client-guid,
# data-hawksearch-search-api). If the fetch starts failing with empty
# results, re-inspect the page for a rotated client GUID.
SEARCH_API = "https://PCAOB.searchapi-na.hawksearch.com/api/v2/search/"
CLIENT_GUID = "e962e95324cb46ef8955c0b09a3904b9"
PAGE_SIZE = 96

INSPECTIONS_URL = (
    "https://pcaobus.org/docs/default-source/generated-reports/"
    "inspecton-reports-csv.csv?download=true"  # (sic — 'inspecton' upstream)
)

# Hawksearch Document fields → registered_firms columns. Every value arrives
# as a single-element list; scalars are unwrapped below.
FIRM_COLS = {
    "firmid": "firm_id",
    "firmname": "firm_name",
    "firmothername": "firm_other_name",
    "firmpredecessorname": "firm_predecessor_name",
    "firmcity": "city",
    "firmstate": "state",
    "firmcountry": "country",
    "firmheadquartersaddress": "headquarters_address",
    "firmregistrationstatus": "registration_status",
    "firmregistrationdate": "registration_date",
    "category": "audit_report_activity",
    "firmsubjecttohfcaa": "is_subject_to_hfcaa",
}

INSPECTION_COLS = {
    "Registration ID": "firm_id",
    "Firm Names": "firm_names",
    "Country": "country",
    "Inspection Report Date": "inspection_report_date",
    "Inspection Year": "inspection_year",
    "Inspection Type": "inspection_type",
    "Global Network": "global_network",
    "Total Audits Reviewed": "total_audits_reviewed",
    "Audits With Part I.A Deficiencies": "audits_with_part_1a_deficiencies",
    "Part I.A Deficiency Rate": "part_1a_deficiency_rate",
    "Includes public quality control criticisms?": "has_quality_control_criticisms",
    "PDF Inspection Report": "report_pdf_url",
}


def fetch_registered_firms() -> pd.DataFrame:
    """Page through the directory's search API, Content Type = Firm."""
    docs = []
    page = 1
    while True:
        body = {
            "ClientGuid": CLIENT_GUID,
            "Keyword": "",
            "PageNo": page,
            "MaxPerPage": PAGE_SIZE,
            "FacetSelections": {"contenttypetitle": ["Firm"]},
        }
        resp = requests.post(SEARCH_API, json=body, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        results = payload["Results"]
        if not results:
            break
        docs.extend(r["Document"] for r in results)
        n_pages = payload["Pagination"]["NofPages"]
        print(f"registered firms: page {page}/{n_pages} ({len(docs)} rows)")
        if page >= n_pages:
            break
        page += 1
        time.sleep(0.5)

    if len(docs) < 3500:  # directory holds ~4.1k firms; a truncated fetch
        raise RuntimeError(f"Only {len(docs)} firm records fetched — "
                           "expected ~4,100; refusing to replace the table.")

    # Keep a dated raw snapshot for debugging / reload without refetch.
    FILES_DIR.mkdir(exist_ok=True)
    snap = FILES_DIR / f"registered_firms_{datetime.now(timezone.utc):%Y%m%d}.json"
    snap.write_text(json.dumps(docs))
    print(f"Raw snapshot: {snap}")

    rows = []
    for doc in docs:
        row = {}
        for src, dst in FIRM_COLS.items():
            val = doc.get(src)
            row[dst] = val[0] if isinstance(val, list) and val else None
        rows.append(row)
    df = pd.DataFrame(rows)
    df["firm_id"] = df["firm_id"].astype("int64")
    df["registration_date"] = pd.to_datetime(
        df["registration_date"], errors="coerce", utc=True)
    df["is_subject_to_hfcaa"] = df["is_subject_to_hfcaa"].map(
        {"True": True, "False": False})
    if df["firm_id"].duplicated().any():
        raise RuntimeError("Duplicate firm_id in directory fetch.")
    return df


def fetch_inspections() -> pd.DataFrame:
    """Official firm-inspection-reports CSV (UTF-16LE, no BOM)."""
    resp = requests.get(INSPECTIONS_URL, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    dest = FILES_DIR / f"inspection_reports_{datetime.now(timezone.utc):%Y%m%d}.csv"
    FILES_DIR.mkdir(exist_ok=True)
    dest.write_bytes(resp.content)
    df = pd.read_csv(dest, encoding="utf-16-le", dtype=str)
    df = df.rename(columns=lambda c: c.strip())[list(INSPECTION_COLS)]
    df = df.rename(columns=INSPECTION_COLS)
    df["firm_id"] = pd.to_numeric(df["firm_id"], errors="coerce").astype("Int64")
    df["inspection_year"] = pd.to_numeric(
        df["inspection_year"], errors="coerce").astype("Int64")
    df["inspection_report_date"] = pd.to_datetime(
        df["inspection_report_date"], format="%d-%b-%Y", errors="coerce", utc=True)
    print(f"inspections: {len(df)} report rows")
    return df


def load() -> None:
    firms = fetch_registered_firms()
    inspections = fetch_inspections()

    load_ts = pd.Timestamp.now(tz="UTC")
    firms["load_ts"] = load_ts
    inspections["load_ts"] = load_ts

    pipeline = dlt.pipeline(
        pipeline_name="pcaob_pipeline",
        destination="bigquery",
        dataset_name=DATASET,
    )
    print("Loading registered_firms ...")
    info = pipeline.run(
        firms,
        table_name="registered_firms",
        write_disposition="replace",
        credentials=gcp_credentials,
    )
    print(info)
    print("Loading firm_inspections ...")
    info = pipeline.run(
        inspections,
        table_name="firm_inspections",
        write_disposition="replace",
        credentials=gcp_credentials,
    )
    print(info)


if __name__ == "__main__":
    load()
