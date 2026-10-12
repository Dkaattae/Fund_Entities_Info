"""Date / month / quarter helpers that decide which period each flow loads.

An off-by-one here silently loads the wrong month (or none): the July 2026
ERA stall and the withdrawn_month overwrite were both in helpers like these.
"""

from datetime import date, datetime

import pytest

from conftest import load_module

flows = load_module("orchestration/flows.py", "flows")
adv_util = load_module("ingestion/adv-form/util.py", "adv_util")
state_download = load_module(
    "ingestion/adv-form/state_adviser_download.py", "state_adviser_download"
)
bd_utils = load_module("ingestion/broker-dealer/utils.py", "utils")
bd_backfill = load_module("ingestion/broker-dealer/backfill.py", "bd_backfill")
form_d_backfill = load_module("ingestion/form-d/backfill.py", "form_d_backfill")


# --- orchestration/flows.py -------------------------------------------------

@pytest.mark.parametrize("today, expected", [
    (date(2026, 9, 28), (2026, 8)),
    (date(2026, 1, 5), (2025, 12)),   # year rollover
    (date(2026, 3, 1), (2026, 2)),
    (date(2026, 12, 31), (2026, 11)),
])
def test_previous_calendar_month(today, expected):
    assert flows.previous_calendar_month(today) == expected


@pytest.mark.parametrize("today, expected", [
    (date(2026, 1, 4), (2025, 4)),    # Q1 -> last year's Q4
    (date(2026, 3, 31), (2025, 4)),
    (date(2026, 4, 1), (2026, 1)),
    (date(2026, 7, 10), (2026, 2)),
    (date(2026, 12, 31), (2026, 3)),
])
def test_previous_calendar_quarter(today, expected):
    assert flows.previous_calendar_quarter(today) == expected


# --- ingestion/adv-form/util.py ---------------------------------------------

def test_generate_months_spans_year_boundary():
    months = adv_util.generate_months(3, 1, current_year_month=(2026, 2))
    assert months == [(2025, 11), (2025, 12), (2026, 1)]


def test_generate_months_single_month():
    assert adv_util.generate_months(1, 1, current_year_month=(2026, 1)) == [(2025, 12)]


@pytest.mark.parametrize("year, month, expected", [
    (2026, 2, "20260228"),
    (2024, 2, "20240229"),   # leap year
    (2026, 4, "20260430"),
    (2026, 12, "20261231"),
])
def test_filing_dates_uses_last_day_of_month(year, month, expected):
    assert adv_util.filing_dates(year, month) == expected


def test_adv_build_url():
    assert adv_util.build_url(2026, 2) == (
        "https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/"
        "ADV_Filing_Data_20260201_20260228.zip"
    )


def test_clean_string():
    raw = "http://www.startingline.vc, @StartingLineVC, (123) 456-7890"
    assert adv_util.clean_string(raw) == "http://www.startingline.vc StartingLineVC 123 456-7890"
    assert adv_util.clean_string(None) is None
    assert adv_util.clean_string(42) == 42


# --- ingestion/adv-form/state_adviser_download.py ---------------------------

def test_state_adviser_build_url_zero_pads():
    assert state_download.build_url(date(2026, 3, 7)).endswith(
        "IA_FIRM_STATE_Feed_03_07_2026.xml.gz"
    )


# --- ingestion/broker-dealer (2-digit 'mm', 'yy' strings) -------------------

@pytest.mark.parametrize("mm, yy, expected", [
    ("01", "26", ("12", "25")),
    ("10", "26", ("09", "26")),
    ("01", "00", ("12", "-1")),  # documents current behaviour at the century edge
])
def test_bd_get_previous_month(mm, yy, expected):
    assert bd_utils.get_previous_month(mm, yy) == expected


@pytest.mark.parametrize("mm, yy, expected", [
    ("12", "25", ("01", "26")),
    ("09", "26", ("10", "26")),
    ("05", "09", ("06", "09")),  # zero-padded year preserved
])
def test_bd_get_later_month(mm, yy, expected):
    assert bd_utils.get_later_month(mm, yy) == expected


def test_bd_previous_and_later_month_round_trip():
    for mm in [f"{m:02d}" for m in range(1, 13)]:
        assert bd_utils.get_later_month(*bd_utils.get_previous_month(mm, "26")) == (mm, "26")


def test_bd_iter_months_inclusive_across_year():
    assert list(bd_backfill.iter_months("11", "25", "02", "26")) == [
        ("11", "25"), ("12", "25"), ("01", "26"), ("02", "26"),
    ]


def test_bd_iter_months_rejects_reversed_range():
    with pytest.raises(ValueError):
        list(bd_backfill.iter_months("02", "26", "01", "26"))


# --- ingestion/form-d/backfill.py -------------------------------------------

class _FrozenDatetime(datetime):
    frozen = datetime(2026, 7, 10)

    @classmethod
    def now(cls, tz=None):
        return cls.frozen


@pytest.fixture
def frozen_now(monkeypatch):
    monkeypatch.setattr(form_d_backfill, "datetime", _FrozenDatetime)
    return _FrozenDatetime


def test_generate_quarters_stops_before_current_quarter(frozen_now):
    # 2026-07-10 is in Q3, so the last complete quarter is 2026 Q2.
    assert form_d_backfill.generate_quarters(2025, 3) == [
        (2025, 3), (2025, 4), (2026, 1), (2026, 2),
    ]


def test_generate_quarters_respects_quarter_cnt(frozen_now):
    assert form_d_backfill.generate_quarters(2025, 1, quarter_cnt=2) == [(2025, 1), (2025, 2)]


def test_generate_quarters_empty_when_start_is_current(frozen_now):
    assert form_d_backfill.generate_quarters(2026, 3) == []


def test_form_d_backfill_raises_when_sec_has_no_file(monkeypatch):
    # A missing quarter must fail the flow, not be skipped silently.
    monkeypatch.setattr(form_d_backfill, "resolve_url", lambda year, quarter: None)
    monkeypatch.setattr(form_d_backfill.dlt, "pipeline", lambda **kwargs: None)
    with pytest.raises(RuntimeError, match="2025Q1 not found"):
        form_d_backfill.backfill(2025, 1, quarter_cnt=1)
