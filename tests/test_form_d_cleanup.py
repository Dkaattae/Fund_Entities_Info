"""ingestion/form-d/cleanup_daily.py: only quarters the bulk data set has
loaded may be deleted from the crawler tables."""

from datetime import date

from conftest import load_module

cleanup = load_module("ingestion/form-d/cleanup_daily.py", "form_d_cleanup_daily")


def test_covered_filter_lists_only_loaded_quarters():
    # 2026Q2 missing (SEC published it late): its crawler rows must survive.
    quarters = [date(2026, 1, 1), date(2026, 7, 1)]
    assert cleanup.covered_filter("d", quarters) == (
        "DATE_TRUNC(d, QUARTER) IN (DATE '2026-01-01', DATE '2026-07-01')"
    )


def test_covered_filter_with_no_quarters_matches_nothing():
    assert cleanup.covered_filter("d", []) == "FALSE"


def test_format_quarters():
    assert cleanup.format_quarters([date(2025, 10, 1), date(2026, 7, 1)]) == "2025Q4, 2026Q3"
    assert cleanup.format_quarters([]) == "none"
