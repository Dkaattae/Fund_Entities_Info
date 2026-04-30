"""Serve the SEC-filings flows as cron-scheduled Prefect deployments.

Run on a long-lived worker:

    python orchestration/serve.py

Schedules (UTC):
  * state-ria-daily    0 6 * * *               every day at 06:00
  * form-d-daily       0 7 * * *               every day at 07:00
  * era-monthly        0 6 5-31 * *            daily 5th-end of every month at 06:00
                                                 (in-flow guard: no-op when current month loaded)
  * form-d-quarterly   0 8 4-31 1,4,7,10 *     daily 4th-end of Jan/Apr/Jul/Oct at 08:00
                                                 (in-flow guard: no-op when target quarter loaded)

Stop with Ctrl+C. Process must stay alive for the cron schedules to fire.
"""

from prefect import serve

from flows import (
    state_ria_daily,
    era_monthly,
    form_d_daily,
    form_d_quarterly,
)


def main() -> None:
    deployments = [
        state_ria_daily.to_deployment(
            name="state-ria-daily",
            cron="0 6 * * *",
            description="Daily state-adviser ingest + dbt run.",
        ),
        era_monthly.to_deployment(
            name="era-monthly",
            cron="0 6 5-31 * *",
            description="SEC ERA monthly ingest. Fires daily after the 5th; "
                        "in-flow guard short-circuits once the previous month is loaded.",
        ),
        form_d_daily.to_deployment(
            name="form-d-daily",
            cron="0 7 * * *",
            description="Daily Form D EDGAR-index crawl + XML parse.",
        ),
        form_d_quarterly.to_deployment(
            name="form-d-quarterly",
            cron="0 8 4-31 1,4,7,10 *",
            description="Form D quarterly bulk + crawler dedupe + dbt refresh. "
                        "Fires daily 4th-end of Jan/Apr/Jul/Oct; "
                        "in-flow guard short-circuits once the target quarter is loaded.",
        ),
    ]
    serve(*deployments)


if __name__ == "__main__":
    main()
