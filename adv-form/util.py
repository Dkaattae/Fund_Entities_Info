from datetime import date
from dateutil.relativedelta import relativedelta
import calendar

def generate_months(start_months_ago=12, end_months_ago=1, current_year_month=None):
    
    if current_year_month:
        today = date(current_year_month[0], current_year_month[1], 1)
    else:
        today = date.today().replace(day=1)
    start = today - relativedelta(months=start_months_ago)
    end = today - relativedelta(months=end_months_ago)

    months = []
    current = start
    while current <= end:
        months.append((current.year, current.month))
        current += relativedelta(months=1)

    return months

def filing_dates(year, month):
    last_day = calendar.monthrange(year, month)[1]
    yyyyMM = f"{year}{month:02d}"
    yyyyMMdd = f"{year}{month:02d}{last_day:02d}"
    return yyyyMMdd


def build_url(year, month):
    yyyyMMdd = filing_dates(year, month)
    year = int(yyyyMMdd[:4])
    yyyyMM = yyyyMMdd[:-2]
    
    return (
        f"https://reports.adviserinfo.sec.gov/reports/foia/"
        f"advFilingData/{year}/"
        f"ADV_Filing_Data_{yyyyMM}01_{yyyyMMdd}.zip"
    )

if __name__ == "__main__":
    url = build_url(2025, 10)
    # print(url)
    months = generate_months(12, 1, (2025,11))
    # print(months)