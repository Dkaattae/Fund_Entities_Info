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
  * broker-dealer-monthly  0 9 5-31 * *        daily 5th-end of every month at 09:00
                                                 (in-flow guard: no-op when month merged)
  * gleif-monthly      0 5 2-8 * *             daily 2nd-8th of every month at 05:00
                                                 (in-flow guard: no-op when month loaded;
                                                  runs before era-monthly so the registry
                                                  mints against a fresh LEI map)

Stop with Ctrl+C. Process must stay alive for the cron schedules to fire.
"""

from prefect import serve

from flows import (
    state_ria_daily,
    era_monthly,
    form_d_daily,
    form_d_quarterly,
    broker_dealer_monthly,
    gleif_monthly,
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
        broker_dealer_monthly.to_deployment(
            name="broker-dealer-monthly",
            cron="0 9 5-31 * *",
            description="Broker-dealer monthly file -> raw load -> dbt master "
                        "rebuild. Fires daily after the 5th; in-flow guard "
                        "short-circuits the load once the month is in raw.",
        ),
        gleif_monthly.to_deployment(
            name="gleif-monthly",
            cron="0 5 2-8 * *",
            description="GLEIF LEI golden copy refresh + LEI match map rebuild. "
                        "Fires daily 2nd-8th, before era-monthly, so the "
                        "provider registry mints against a fresh map; in-flow "
                        "guard short-circuits once the month is loaded.",
        ),
    ]
    serve(*deployments)


if __name__ == "__main__":
    main()
