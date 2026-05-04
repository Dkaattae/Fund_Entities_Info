import pandas as pd
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Recently Formed Funds", layout="wide")


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
            funds_with_shared_persons
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

# Summary strip
c1, c2, c3 = st.columns(3)
c1.metric("Total funds shown", len(df))
c2.metric("With linked adviser", int((df["relationship_to_adviser"] != "no_adv_found").sum()))
c3.metric("With shared-person connections", int((df["shared_fund_count"] > 0).sum()))

st.divider()

# Main table
DISPLAY_COLS = {
    "primary_issuer_name": "Fund Name",
    "filing_date": "Filed",
    "investment_fund_type": "Type",
    "total_offering_amount_numeric": "Offering ($)",
    "adviser_legal_name": "Adviser",
    "relationship_to_adviser": "Adviser Status",
    "shared_fund_count": "Shared Connections",
}
display_df = df[list(DISPLAY_COLS.keys())].rename(columns=DISPLAY_COLS)
display_df["Offering ($)"] = display_df["Offering ($)"].apply(fmt_currency)

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

row = df.iloc[selected_rows[0]].to_dict()

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

# --- Related persons ---
persons = row.get("related_persons") or []
with st.expander(f"Related Persons ({len(persons)})"):
    if persons:
        persons_rows = []
        for p in persons:
            roles = [
                r for r in [p.get("relationship_1"), p.get("relationship_2"), p.get("relationship_3")]
                if r
            ]
            persons_rows.append(
                {
                    "Name": p.get("full_name", ""),
                    "Roles": ", ".join(roles),
                    "Promoter": "Yes" if p.get("is_promoter") else "",
                }
            )
        st.dataframe(pd.DataFrame(persons_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No related persons on record.")

# --- Funds sharing a related person ---
shared = row.get("funds_with_shared_persons") or []
with st.expander(f"Other Funds with Shared Persons ({row.get('shared_fund_count', 0)})"):
    if shared:
        shared_rows = []
        for s in shared:
            shared_rows.append(
                {
                    "Fund Name": s.get("shared_fund_name", ""),
                    "File No.": s.get("shared_fund_file_num", ""),
                    "CIK": s.get("shared_fund_cik", ""),
                    "Filing Date": str(s.get("shared_fund_filing_date", "")),
                    "Via Person(s)": ", ".join(s.get("via_persons") or []),
                }
            )
        st.dataframe(pd.DataFrame(shared_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No other funds found with shared related persons.")
