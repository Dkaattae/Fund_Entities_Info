"""Prefect flows for the SEC-filings pipelines.

Flows:
  - state_ria_daily       state-adviser snapshot      (daily)
  - era_monthly           SEC ERA monthly archive     (daily-in-window, idempotent)
  - form_d_daily          Form D EDGAR daily index    (daily)
  - form_d_quarterly      Form D bulk + dedupe        (daily-in-window, idempotent)

The "monthly" / "quarterly" flows are scheduled daily during the SEC release
window (see serve.py crons) and short-circuit when the target period is
already in BigQuery — the cron picks up day-of-release, the in-flow guard
stops re-runs once the data lands.

Each task shells out to existing CLI scripts so credential handling stays in
one place (BIGQUERY_SERVICE_ACCOUNT_JSON, picked up by both the ingest
scripts and transform/sec_filings/run_dbt.py).
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date
from pathlib import Path

from prefect import flow, task, get_run_logger


REPO_ROOT         = Path(__file__).resolve().parent.parent
ADV_INGEST_DIR    = REPO_ROOT / "ingestion" / "adv-form"
FORM_D_INGEST_DIR = REPO_ROOT / "ingestion" / "form-d"
TRANSFORM_DIR     = REPO_ROOT / "transform" / "sec_filings"


def _run(cmd: list[str], cwd: Path) -> None:
    log = get_run_logger()
    log.info("$ %s  (cwd=%s)", " ".join(cmd), cwd)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def _bq_client():
    from google.cloud import bigquery
    creds = json.loads(os.environ["BIGQUERY_SERVICE_ACCOUNT_JSON"])
    return bigquery.Client.from_service_account_info(creds), creds["project_id"]


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def previous_calendar_month(today: date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def previous_calendar_quarter(today: date) -> tuple[int, int]:
    current_q = (today.month - 1) // 3 + 1
    if current_q == 1:
        return today.year - 1, 4
    return today.year, current_q - 1


# ---------------------------------------------------------------------------
# Idempotency checks
# ---------------------------------------------------------------------------

@task
def is_era_month_loaded(year: int, month: int) -> bool:
    client, project = _bq_client()
    q = f"""
        SELECT COUNT(*) AS n
        FROM `{project}.era_adv.base`
        WHERE EXTRACT(YEAR  FROM SAFE.PARSE_DATE('%m/%d/%Y', date_submitted)) = {year}
          AND EXTRACT(MONTH FROM SAFE.PARSE_DATE('%m/%d/%Y', date_submitted)) = {month}
    """
    n = next(client.query(q).result()).n
    return n > 0


@task
def is_form_d_quarter_loaded(year: int, quarter: int) -> bool:
    client, project = _bq_client()
    start_month = (quarter - 1) * 3 + 1
    end_month   = quarter * 3
    q = f"""
        SELECT COUNT(*) AS n
        FROM `{project}.form_d_filings.form_d_submission`
        WHERE SAFE.PARSE_DATE('%d-%b-%Y', filing_date)
              BETWEEN DATE '{year}-{start_month:02d}-01'
                  AND LAST_DAY(DATE '{year}-{end_month:02d}-01')
    """
    n = next(client.query(q).result()).n
    return n > 0


# ---------------------------------------------------------------------------
# Ingest tasks
# ---------------------------------------------------------------------------

@task(retries=2, retry_delay_seconds=300)
def ingest_state_adviser() -> None:
    _run(["python", "state_adviser_ingest.py"], cwd=ADV_INGEST_DIR)


@task(retries=1, retry_delay_seconds=600)
def ingest_era_monthly() -> None:
    _run(
        ["python", "-c", "from era_ingestion import update_monthly; update_monthly()"],
        cwd=ADV_INGEST_DIR,
    )


@task(retries=2, retry_delay_seconds=300)
def crawl_form_d_index() -> None:
    _run(["python", "form_d_crawler.py"], cwd=FORM_D_INGEST_DIR)


@task(retries=1, retry_delay_seconds=600)
def parse_form_d_pending() -> None:
    _run(["python", "form_d_detail.py"], cwd=FORM_D_INGEST_DIR)


@task(retries=1, retry_delay_seconds=900)
def backfill_form_d_quarter(year: int, quarter: int) -> None:
    """Backfill exactly one quarter — the bulk 'backfill()' helper accepts
    a (start_year, start_quarter) plus quarter_cnt=1 to load just one ZIP."""
    _run(
        ["python", "-c",
         f"from backfill import backfill; backfill({year}, {quarter}, quarter_cnt=1)"],
        cwd=FORM_D_INGEST_DIR,
    )


@task(retries=0)
def cleanup_form_d_daily_overlap() -> None:
    _run(["python", "cleanup_daily.py", "--execute"], cwd=FORM_D_INGEST_DIR)


@task(retries=1, retry_delay_seconds=120)
def dbt_run(select: str) -> None:
    _run(["python", "run_dbt.py", "run", "--select", select], cwd=TRANSFORM_DIR)


@task(retries=0)
def dbt_test(select: str) -> None:
    _run(["python", "run_dbt.py", "test", "--select", select], cwd=TRANSFORM_DIR)


# ---------------------------------------------------------------------------
# Flows
# ---------------------------------------------------------------------------

@flow(name="state-ria-daily", log_prints=True)
def state_ria_daily() -> None:
    ingest_state_adviser()
    dbt_run("tag:state_adv")
    dbt_test("tag:state_adv")


@flow(name="era-monthly", log_prints=True)
def era_monthly() -> None:
    """Daily-in-window: short-circuits once the previous calendar month's
    SEC ERA archive is in BigQuery."""
    log = get_run_logger()
    target_year, target_month = previous_calendar_month(date.today())
    log.info("Target ERA month: %d-%02d", target_year, target_month)

    if is_era_month_loaded(target_year, target_month):
        log.info("Already loaded — skipping.")
        return

    ingest_era_monthly()
    dbt_run("tag:era")
    dbt_test("tag:era")


@flow(name="form-d-daily", log_prints=True)
def form_d_daily() -> None:
    """Daily EDGAR-index crawl + per-filing XML parse into the crawler dataset."""
    crawl_form_d_index()
    parse_form_d_pending()
    # NOTE: dbt sources currently read only the bulk dataset (form_d_filings),
    # not the crawler dataset (formd_filings_crawler). Daily-fresh rows won't
    # show up in marts until the crawler tables are unioned into staging.
    dbt_run("tag:form_d")


@flow(name="form-d-quarterly", log_prints=True)
def form_d_quarterly() -> None:
    """Daily-in-window: short-circuits once the previous calendar quarter's
    SEC bulk ZIP is in BigQuery. On first successful load, dedupes the
    crawler tables and refreshes form_d marts."""
    log = get_run_logger()
    target_year, target_q = previous_calendar_quarter(date.today())
    log.info("Target Form D quarter: %dQ%d", target_year, target_q)

    if is_form_d_quarter_loaded(target_year, target_q):
        log.info("Already loaded — skipping.")
        return

    backfill_form_d_quarter(target_year, target_q)
    cleanup_form_d_daily_overlap()
    dbt_run("tag:form_d")
    dbt_test("tag:form_d")


if __name__ == "__main__":
    import sys

    routes = {
        "state":            state_ria_daily,
        "era":              era_monthly,
        "form_d_daily":     form_d_daily,
        "form_d_quarterly": form_d_quarterly,
    }
    arg = sys.argv[1] if len(sys.argv) > 1 else "state"
    fn = routes.get(arg)
    if fn is None:
        sys.exit(f"Usage: python flows.py [{'|'.join(routes)}]")
    fn()
