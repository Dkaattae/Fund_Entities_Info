"""Ingest the GLEIF LEI golden copy (Level 1, LEI-CDF v3.1) into BigQuery.

GLEIF publishes a full "golden copy" of all ~3.4M LEI records three times a
day, free of charge. This loads a slim projection of it (the full CSV has 338
columns) for service-provider identity matching — see project_plan.md
"Problem 3 — Non-US fund admins missing".

Tables (dataset `gleif`, write_disposition=replace):
  lei_records  one row per LEI: legal name, legal/HQ address, jurisdiction,
               category, status, registration status/dates, associated LEI.
  lei_names    long format, one row per (lei, name): the legal name plus all
               OtherEntityNames and TransliteratedOtherEntityNames variants —
               this is the table dbt matches fund-admin filing names against.

Usage:
  python gleif_ingestion.py              # download latest golden copy, load
  python gleif_ingestion.py <csv.zip>    # load an already-downloaded file

This is a manual / on-demand load (no schedule): LEI records change slowly
and the matching layer only needs a reasonably current snapshot. Re-run it
before re-tuning fund-admin matching, or if coverage looks stale.
"""

import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Iterator

import dlt
import pandas as pd
import requests

service_account_json_str = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")
if not service_account_json_str:
    raise ValueError("BIGQUERY_SERVICE_ACCOUNT_JSON not set.")

gcp_credentials = json.loads(service_account_json_str)

PUBLISHES_API = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest"
HEADERS = {"User-Agent": "HedgeFundNet katechen150621@gmail.com"}
FILES_DIR = Path(__file__).resolve().parent / "files"

DATASET = "gleif"
CHUNK_ROWS = 250_000

RECORD_COLS = {
    "LEI": "lei",
    "Entity.LegalName": "legal_name",
    "Entity.LegalAddress.City": "legal_city",
    "Entity.LegalAddress.Region": "legal_region",
    "Entity.LegalAddress.Country": "legal_country",
    "Entity.HeadquartersAddress.City": "hq_city",
    "Entity.HeadquartersAddress.Region": "hq_region",
    "Entity.HeadquartersAddress.Country": "hq_country",
    "Entity.LegalJurisdiction": "legal_jurisdiction",
    "Entity.EntityCategory": "entity_category",
    "Entity.LegalForm.EntityLegalFormCode": "legal_form_code",
    "Entity.EntityStatus": "entity_status",
    # NB: Entity.AssociatedEntity.AssociatedLEI is deprecated in LEI-CDF v3
    # and 100% empty in the golden copy — parent/manager links are in the
    # Level 2 relationship files (not ingested yet).
    "Registration.InitialRegistrationDate": "initial_registration_date",
    "Registration.LastUpdateDate": "last_update_date",
    "Registration.RegistrationStatus": "registration_status",
}
TIMESTAMP_COLS = ["initial_registration_date", "last_update_date"]

LEGAL_NAME_COL = "Entity.LegalName"
OTHER_NAME_COLS = [
    (f"Entity.OtherEntityNames.OtherEntityName.{i}",
     f"Entity.OtherEntityNames.OtherEntityName.{i}.type", i)
    for i in range(1, 6)
]
TRANSLIT_NAME_COLS = [
    (f"Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName.{i}",
     f"Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName.{i}.type", 10 + i)
    for i in range(1, 6)
]


def download_latest() -> Path:
    """Download the latest full golden-copy CSV zip; skip if already on disk."""
    meta = requests.get(PUBLISHES_API, headers=HEADERS, timeout=60).json()
    url = meta["data"]["lei2"]["full_file"]["csv"]["url"]
    dest = FILES_DIR / url.rsplit("/", 1)[-1]
    if dest.exists():
        print(f"Already downloaded: {dest}")
        return dest
    FILES_DIR.mkdir(exist_ok=True)
    print(f"Downloading {url}")
    with requests.get(url, headers=HEADERS, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for block in resp.iter_content(chunk_size=1 << 20):
                f.write(block)
    print(f"Saved {dest} ({dest.stat().st_size / 1e6:.0f} MB)")
    return dest


def _open_csv(zip_path: Path):
    zf = zipfile.ZipFile(zip_path)
    member = zf.namelist()[0]
    return io.TextIOWrapper(zf.open(member), encoding="utf-8")


def iter_lei_records(zip_path: Path) -> Iterator[pd.DataFrame]:
    with _open_csv(zip_path) as f:
        for chunk in pd.read_csv(f, usecols=list(RECORD_COLS), dtype=str,
                                 chunksize=CHUNK_ROWS):
            chunk = chunk.rename(columns=RECORD_COLS)
            for col in TIMESTAMP_COLS:
                chunk[col] = pd.to_datetime(chunk[col], errors="coerce", utc=True)
            yield chunk


def iter_lei_names(zip_path: Path) -> Iterator[pd.DataFrame]:
    usecols = (["LEI", LEGAL_NAME_COL]
               + [c for c, t, _ in OTHER_NAME_COLS + TRANSLIT_NAME_COLS]
               + [t for c, t, _ in OTHER_NAME_COLS + TRANSLIT_NAME_COLS])
    with _open_csv(zip_path) as f:
        for chunk in pd.read_csv(f, usecols=usecols, dtype=str,
                                 chunksize=CHUNK_ROWS):
            parts = [pd.DataFrame({
                "lei": chunk["LEI"],
                "name": chunk[LEGAL_NAME_COL],
                "name_type": "LEGAL",
                "name_rank": 0,
            })]
            for name_col, type_col, rank in OTHER_NAME_COLS + TRANSLIT_NAME_COLS:
                parts.append(pd.DataFrame({
                    "lei": chunk["LEI"],
                    "name": chunk[name_col],
                    "name_type": chunk[type_col].fillna("OTHER"),
                    "name_rank": rank,
                }))
            long_df = pd.concat(parts, ignore_index=True)
            long_df = long_df[long_df["name"].notna() & (long_df["name"].str.strip() != "")]
            long_df = long_df.drop_duplicates(subset=["lei", "name", "name_type"])
            yield long_df


def load(zip_path: Path) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="gleif_pipeline",
        destination="bigquery",
        dataset_name=DATASET,
    )
    print("Loading lei_records ...")
    info = pipeline.run(
        iter_lei_records(zip_path),
        table_name="lei_records",
        write_disposition="replace",
        credentials=gcp_credentials,
    )
    print(info)
    print("Loading lei_names ...")
    info = pipeline.run(
        iter_lei_names(zip_path),
        table_name="lei_names",
        write_disposition="replace",
        credentials=gcp_credentials,
    )
    print(info)


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else download_latest()
    load(path)
