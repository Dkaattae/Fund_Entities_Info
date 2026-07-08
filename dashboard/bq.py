import json
import os

import streamlit as st
from google.cloud import bigquery


@st.cache_resource
def bq_client():
    raw = os.environ.get("BIGQUERY_SERVICE_ACCOUNT_JSON") or st.secrets.get(
        "BIGQUERY_SERVICE_ACCOUNT_JSON"
    )
    if not raw:
        st.error("BIGQUERY_SERVICE_ACCOUNT_JSON not set.")
        st.stop()
    creds = json.loads(raw)
    return bigquery.Client.from_service_account_info(creds), creds["project_id"]


def run_query(sql: str):
    """Run a BigQuery query and return a DataFrame. On failure, show a
    readable error and halt the page instead of crashing with a traceback."""
    client, _ = bq_client()
    try:
        return client.query(sql).to_dataframe()
    except Exception as exc:
        st.error(f"BigQuery query failed:\n\n```\n{exc}\n```")
        st.stop()
