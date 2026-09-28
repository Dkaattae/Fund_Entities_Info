"""Fuzzy fund-admin name matching (transform/sec_filings/scripts/discover_unknown_fund_admins.py).

These Python functions mirror the normalize_provider_name /
token_set_similarity / edit_distance_ratio dbt macros; the suggestions they
make end up in seeds/fund_admin_aliases.csv.
"""

import pytest

from conftest import REPO_ROOT, load_module

m = load_module(
    "transform/sec_filings/scripts/discover_unknown_fund_admins.py",
    "discover_unknown_fund_admins",
)


@pytest.mark.parametrize("raw, expected", [
    ("SS&C Technologies, Inc.", "ss c technologies"),
    ("The Bank of New York Mellon Corp", "bank of new york mellon"),
    ("NAV Fund Services LLC", "nav fund services"),
    ("  Apex  Fund   Services (Ltd.) ", "apex fund services"),
    ("Coinbase", "coinbase"),  # 'co' is only stripped as a whole token
])
def test_normalize_str(raw, expected):
    assert m.normalize_str(raw) == expected


def test_token_set_ratio_is_order_independent():
    assert m.token_set_ratio("nav fund services", "fund services nav") == 1.0
    assert m.token_set_ratio("apex fund services", "apex group") == pytest.approx(1 / 4)
    assert m.token_set_ratio("", "anything") == 0.0


def test_edit_distance_ratio_catches_typos():
    assert m.edit_distance_ratio("advisors", "advisrs") == pytest.approx(7 / 8)
    assert m.edit_distance_ratio("same", "same") == 1.0
    assert m.edit_distance_ratio("", "") == 0.0
    assert m._levenshtein("kitten", "sitting") == 3


def test_blended_ratio_takes_the_better_metric():
    a, b = "citco fund services", "citco fund servics"
    assert m.blended_ratio(a, b) == m.edit_distance_ratio(a, b) > m.token_set_ratio(a, b)


CANONICALS = ["Citco Fund Services", "NAV Fund Services", "SS&C Technologies"]


def test_suggest_canonical_matches_above_threshold():
    name, score = m.suggest_canonical("Citco Fund Services (Cayman) Ltd", CANONICALS)
    # 'cayman' makes Jaccard 3/4, below 0.92 -> falls back to raw
    assert name == "Citco Fund Services (Cayman) Ltd"
    assert score < m.SUGGEST_THRESHOLD

    name, score = m.suggest_canonical("Fund Services NAV, LLC", CANONICALS)
    assert (name, score) == ("NAV Fund Services", 1.0)

    name, score = m.suggest_canonical("Citco Fund Servics Inc", CANONICALS)
    assert name == "Citco Fund Services" and score >= m.SUGGEST_THRESHOLD


def test_suggest_canonical_ignores_very_short_names():
    assert m.suggest_canonical("Co.", CANONICALS) == ("Co.", 0.0)


def test_seed_file_loads():
    raw_names, canonicals = m.load_seed_rows(
        REPO_ROOT / "transform/sec_filings/seeds/fund_admin_aliases.csv"
    )
    assert raw_names and canonicals
    assert all(r == r.strip().lower() for r in raw_names)
    assert len(canonicals) == len(set(canonicals))
