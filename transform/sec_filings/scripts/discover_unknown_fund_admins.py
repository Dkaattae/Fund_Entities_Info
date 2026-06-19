#!/usr/bin/env python3
"""
Finds FUND_ADMIN entries in BigQuery that have no match in seeds/fund_admin_aliases.csv
and appends them as new rows. For each unmatched raw_name, suggests a canonical_name
by token-set similarity against the canonical names already in the seed — mirroring the
token_set_similarity macro used in int_service_provider_links.sql. A match at or above
the threshold is written as the suggested canonical_name; otherwise the row falls back
to a placeholder (canonical_name = raw_name).

After running, open seeds/fund_admin_aliases.csv, review the suggested rows (each
suggestion is printed with its score), correct anything wrong, then re-run `dbt seed`.

Usage:
    python transform/sec_filings/scripts/discover_unknown_fund_admins.py [--dataset sec_filings_intermediate]
"""

import argparse
import csv
import json
import os
import re
from pathlib import Path

from google.cloud import bigquery

SEED_PATH = Path(__file__).parent.parent / "seeds" / "fund_admin_aliases.csv"

# Suggest a canonical only when token-set similarity is at least this high.
# Mirrors the 0.92 auto-apply threshold in int_service_provider_links.sql so the
# script's suggestions line up with what the model would fuzzy-match at runtime.
SUGGEST_THRESHOLD = 0.92

# Entity suffixes stripped during normalization — kept in sync with the
# normalize_provider_name() dbt macro so Python tokens match the SQL tokens.
_ENTITY_SUFFIXES = {
    "llc", "llp", "lp", "lllp", "inc", "incorporated", "corp", "corporation",
    "co", "company", "ltd", "limited", "plc", "gmbh", "ag", "sa", "nv", "bv",
    "partners", "partnership", "trust", "the",
}

# Query unknown fund admins: in BigQuery but not matched to any alias.
# alias_canonical_name is NULL when the raw_name had no seed match.
QUERY = """
SELECT
    raw_name,
    COUNT(DISTINCT filing_id) AS filing_count
FROM `{project}.{dataset}.int_service_provider_links`
WHERE provider_type = 'FUND_ADMIN'
  AND alias_canonical_name IS NULL
  AND raw_name IS NOT NULL
GROUP BY raw_name
ORDER BY filing_count DESC, raw_name
"""


def normalize_str(name: str) -> str:
    """Light normalization matching normalize_provider_name(): lowercase, drop
    non-alphanumerics, strip entity suffixes, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return " ".join(t for t in cleaned.split() if t not in _ENTITY_SUFFIXES)


def token_set_ratio(a: str, b: str) -> float:
    """Jaccard similarity over token sets — mirrors token_set_similarity macro."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def edit_distance_ratio(a: str, b: str) -> float:
    """Character-level similarity — mirrors edit_distance_ratio macro."""
    longest = max(len(a), len(b))
    if longest == 0:
        return 0.0
    return (longest - _levenshtein(a, b)) / longest


def blended_ratio(a: str, b: str) -> float:
    """GREATEST(token-set, edit-distance) — mirrors the model's score expression."""
    return max(token_set_ratio(a, b), edit_distance_ratio(a, b))


def load_seed_rows(path: Path) -> tuple[set[str], list[str]]:
    """Returns (existing raw_names lowercased, distinct canonical_names)."""
    if not path.exists():
        return set(), []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_raw: set[str] = set()
        canonicals: dict[str, None] = {}  # ordered, deduped
        for row in reader:
            existing_raw.add(row["raw_name"].strip().lower())
            canon = (row.get("canonical_name") or "").strip()
            if canon:
                canonicals[canon] = None
    return existing_raw, list(canonicals)


def suggest_canonical(raw_name: str, canonicals: list[str]) -> tuple[str, float]:
    """Best canonical match for raw_name by token-set ratio, plus its score.
    Falls back to (raw_name, 0.0) when nothing clears the threshold."""
    raw_norm = normalize_str(raw_name)
    if len(raw_norm) < 4:
        return raw_name, 0.0
    best_name, best_score = raw_name, 0.0
    for canon in canonicals:
        canon_norm = normalize_str(canon)
        if len(canon_norm) < 4:
            continue
        score = blended_ratio(raw_norm, canon_norm)
        if score > best_score:
            best_name, best_score = canon, score
    if best_score >= SUGGEST_THRESHOLD:
        return best_name, best_score
    return raw_name, best_score


def append_to_seed(path: Path, new_rows: list[dict]) -> None:
    file_empty = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["raw_name", "canonical_name"])
        if file_empty:
            writer.writeheader()
        for row in new_rows:
            writer.writerow({"raw_name": row["raw_name"], "canonical_name": row["canonical_name"]})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="sec_filings_intermediate", help="BigQuery dataset name")
    args = parser.parse_args()

    creds_json = os.environ.get("BIGQUERY_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise SystemExit("BIGQUERY_SERVICE_ACCOUNT_JSON env var is not set")

    creds = json.loads(creds_json)
    client = bigquery.Client.from_service_account_info(creds)
    project_id = creds["project_id"]

    print(f"Querying {project_id}.{args.dataset}.int_service_provider_links ...")
    rows = list(client.query(QUERY.format(project=project_id, dataset=args.dataset)).result())

    existing, canonicals = load_seed_rows(SEED_PATH)
    new_rows = []
    for r in rows:
        if r["raw_name"].strip().lower() in existing:
            continue
        canonical, score = suggest_canonical(r["raw_name"], canonicals)
        new_rows.append(
            {
                "raw_name": r["raw_name"],
                "canonical_name": canonical,
                "filing_count": r["filing_count"],
                "score": score,
                "suggested": canonical != r["raw_name"],
            }
        )

    if not new_rows:
        print("No new fund admins found — seed is up to date.")
        return

    suggested = sum(1 for r in new_rows if r["suggested"])
    print(f"\nFound {len(new_rows)} unmatched fund admins ({suggested} with a suggested canonical):\n")
    for r in new_rows:
        if r["suggested"]:
            tag = f"-> {r['canonical_name']}  (score {r['score']:.2f})"
        else:
            tag = "-> (placeholder, no confident match — fill in manually)"
        print(f"  {r['filing_count']:>5} filings  {r['raw_name']}  {tag}")

    append_to_seed(SEED_PATH, new_rows)
    print(f"\nAppended {len(new_rows)} rows to {SEED_PATH}")
    print("Next: review the suggested canonical_names (especially borderline scores),")
    print("      correct any placeholders, then run: dbt seed && dbt run -s int_service_provider_links+")


if __name__ == "__main__":
    main()
