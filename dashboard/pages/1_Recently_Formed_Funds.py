import pandas as pd
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Recently Formed Funds", layout="wide")


def _to_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        return list(val)
    except TypeError:
        return []


def _struct_get(item, key: str, default="") -> str:
    if isinstance(item, dict):
        return item.get(key, default)
    try:
        return getattr(item, key, default)
    except Exception:
        return default


@st.cache_data(ttl=3600)
def load_funds() -> pd.DataFrame:
    client, project = bq_client()
    query = f"""
        SELECT
            accession_number,
            file_num,
            primary_issuer_cik,
            filing_date,
            primary_issuer_name,
            investment_fund_type,
            jurisdiction_of_inc,
            year_of_inc,
            total_offering_amount_numeric,
            minimum_investment_accepted,
            claims_3c1, claims_3c7, claims_506b, claims_506c,
            adviser_legal_name,
            adviser_business_name,
            fallback_promoter_name,
            relationship_to_adviser,
            adviser_first_adv_filing_date,
            related_persons,
            shared_fund_count,
            funds_with_shared_persons,
            edgar_filing_url,
            edgar_fund_history_url
        FROM `{project}.sec_filings_marts.newly_emerging_funds`
        ORDER BY filing_date DESC
        LIMIT 500
    """
    return client.query(query).to_dataframe()


def fmt_currency(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    return f"${val:,.0f}"


def exemption_badges(row) -> str:
    labels = {
        "claims_3c1": "3(c)(1)",
        "claims_3c7": "3(c)(7)",
        "claims_506b": "506(b)",
        "claims_506c": "506(c)",
    }
    active = [label for col, label in labels.items() if row.get(col)]
    return ", ".join(active) if active else "—"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.title("Recently Formed Funds")
st.caption(
    "SEC Form D filings — pooled investment funds with no prior filing history. "
    "Select a row to inspect details."
)

df = load_funds()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
SHARED_CONN_LABELS = ["0", "1–10", "10–30", "30+"]

def _shared_conn_bucket(n) -> str:
    if pd.isna(n) or n == 0:
        return "0"
    if n <= 10:
        return "1–10"
    if n <= 30:
        return "10–30"
    return "30+"

with st.sidebar:
    st.header("Filters")

    type_options = sorted(df["investment_fund_type"].dropna().unique().tolist())
    selected_types = st.multiselect("Fund Type", type_options, default=type_options)

    selected_buckets = st.multiselect(
        "Shared Connections",
        SHARED_CONN_LABELS,
        default=SHARED_CONN_LABELS,
    )

df["_shared_bucket"] = df["shared_fund_count"].apply(_shared_conn_bucket)

filtered = df[
    df["investment_fund_type"].isin(selected_types) &
    df["_shared_bucket"].isin(selected_buckets)
]

# Summary strip
c1, c2, c3 = st.columns(3)
c1.metric("Funds shown", len(filtered))
c2.metric("With linked adviser", int((filtered["relationship_to_adviser"] != "no_adv_found").sum()))
c3.metric("With shared-person connections", int((filtered["shared_fund_count"] > 0).sum()))

st.divider()

# Main table
DISPLAY_COLS = {
    "primary_issuer_name":          "Fund Name",
    "filing_date":                  "Filed",
    "investment_fund_type":         "Type",
    "total_offering_amount_numeric": "Offering ($)",
    "adviser_legal_name":           "Adviser",
    "shared_fund_count":            "Shared Connections",
}
display_df = filtered[list(DISPLAY_COLS.keys())].rename(columns=DISPLAY_COLS)
display_df["Offering ($)"] = filtered["total_offering_amount_numeric"].apply(fmt_currency)

event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ---------------------------------------------------------------------------
# Detail panel
# ---------------------------------------------------------------------------

selected_rows = event.selection.rows
if not selected_rows:
    st.caption("Click a row above to see fund details.")
    st.stop()

row = filtered.iloc[selected_rows[0]].to_dict()

st.divider()
adviser_display = (
    row.get("adviser_legal_name")
    or row.get("adviser_business_name")
    or row.get("fallback_promoter_name")
    or "—"
)

st.subheader(row["primary_issuer_name"])

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Filing Date", str(row["filing_date"]))
    st.metric("Year of Inc.", str(row["year_of_inc"]) if row.get("year_of_inc") else "—")
    st.metric("Jurisdiction", row.get("jurisdiction_of_inc") or "—")
with col2:
    st.metric("Offering Size", fmt_currency(row.get("total_offering_amount_numeric")))
    st.metric("Min. Investment", fmt_currency(row.get("minimum_investment_accepted")))
    st.metric("Fund Type", row.get("investment_fund_type") or "—")
with col3:
    st.metric("Adviser", adviser_display)
    st.metric("Adviser Status", row.get("relationship_to_adviser") or "—")
    adv_first = row.get("adviser_first_adv_filing_date")
    st.metric("Adviser First ADV", str(adv_first) if adv_first else "—")

st.caption(f"CIK: {row.get('primary_issuer_cik') or '—'}  |  "
           f"File No.: {row.get('file_num') or '—'}  |  "
           f"Exemptions: {exemption_badges(row)}")

link_col1, link_col2 = st.columns(2)
if row.get("edgar_filing_url"):
    link_col1.link_button("View filing on EDGAR", row["edgar_filing_url"])
if row.get("edgar_fund_history_url"):
    link_col2.link_button("All filings for this fund", row["edgar_fund_history_url"])

# --- Related persons ---
persons = _to_list(row.get("related_persons"))
with st.expander(f"Related Persons ({len(persons)})"):
    if persons:
        persons_rows = []
        for p in persons:
            roles = [
                r for r in [
                    _struct_get(p, "relationship_1"),
                    _struct_get(p, "relationship_2"),
                    _struct_get(p, "relationship_3"),
                ]
                if r
            ]
            persons_rows.append({
                "Name":     _struct_get(p, "full_name"),
                "Roles":    ", ".join(roles),
                "Promoter": "Yes" if _struct_get(p, "is_promoter") else "",
            })
        st.dataframe(pd.DataFrame(persons_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No related persons on record.")

# --- Funds sharing a related person ---
shared = _to_list(row.get("funds_with_shared_persons"))
with st.expander(f"Other Funds with Shared Persons ({row.get('shared_fund_count', 0)})"):
    if shared:
        shared_rows = [{
            "Fund Name":    _struct_get(s, "shared_fund_name"),
            "File No.":     _struct_get(s, "shared_fund_file_num"),
            "CIK":          _struct_get(s, "shared_fund_cik"),
            "Filing Date":  str(_struct_get(s, "shared_fund_filing_date")),
            "Via Person(s)": ", ".join(_to_list(_struct_get(s, "via_persons", []))),
        } for s in shared if s is not None]
        st.dataframe(pd.DataFrame(shared_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No other funds found with shared related persons.")
