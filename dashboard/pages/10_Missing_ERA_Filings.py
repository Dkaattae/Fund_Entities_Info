import pandas as pd
import streamlit as st

from bq import bq_client, run_query

st.set_page_config(page_title="Missing ERA Filings", layout="wide")

st.title("Missing ERA Filings")
st.caption(
    "SEC ERA (Form ADV) advisers past their annual amendment due date — fiscal year end "
    "+ 90 days — with no filing for the current reporting year. Advisers that wound down "
    "via a final report are excluded (their exits show on Fund Closures); everyone here "
    "is presumed active and delinquent."
)


def fmt_aum(x) -> str:
    if pd.isna(x):
        return "—"
    x = float(x)
    if x >= 1e9:
        return f"${x/1e9:,.1f}B"
    if x >= 1e6:
        return f"${x/1e6:,.0f}M"
    return f"${x:,.0f}"


@st.cache_data(ttl=3600)
def load_compliance() -> pd.DataFrame:
    _, project = bq_client()
    df = run_query(f"""
        SELECT
            entity_key, legal_name, business_name,
            assets_under_management, fiscal_year_end,
            main_city, main_state,
            current_reporting_year, due_date, last_filing_date, days_overdue
        FROM `{project}.sec_filings_marts.adviser_filing_compliance`
        ORDER BY days_overdue DESC
    """)
    df["assets_under_management"] = pd.to_numeric(df["assets_under_management"], errors="coerce")
    df["days_overdue"] = pd.to_numeric(df["days_overdue"], errors="coerce")
    return df


df = load_compliance()
current_year = int(df["current_reporting_year"].iloc[0]) if len(df) else None

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    fye_options = sorted(df["fiscal_year_end"].dropna().unique().tolist())
    selected_fye = st.multiselect("Fiscal year end", fye_options, default=fye_options)

    state_options = sorted(df["main_state"].dropna().unique().tolist())
    selected_states = st.multiselect(
        "State", state_options, default=[],
        help="Empty = all states.",
    )

    min_days = st.number_input("Min days overdue", min_value=0, value=0, step=30)

filtered = df.copy()
if selected_fye:
    filtered = filtered[filtered["fiscal_year_end"].isin(selected_fye)]
if selected_states:
    filtered = filtered[filtered["main_state"].isin(selected_states)]
if min_days:
    filtered = filtered[filtered["days_overdue"] >= min_days]

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
title_year = f" — {current_year} filing overdue" if current_year else ""
st.subheader(f"Overdue advisers{title_year}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Advisers overdue", f"{len(filtered):,}")
c2.metric("Avg days overdue",
          f"{filtered['days_overdue'].mean():.0f}" if len(filtered) else "—")
c3.metric("Max days overdue",
          f"{filtered['days_overdue'].max():.0f}" if len(filtered) else "—")
c4.metric("Total AUM overdue",
          fmt_aum(filtered["assets_under_management"].sum()) if len(filtered) else "—")

# ---------------------------------------------------------------------------
# Detail table
# ---------------------------------------------------------------------------
display = pd.DataFrame({
    "Adviser":      filtered["business_name"].fillna(filtered["legal_name"]),
    "AUM":          filtered["assets_under_management"].apply(fmt_aum),
    "FYE":          filtered["fiscal_year_end"],
    "Due Date":     filtered["due_date"].astype(str),
    "Days Overdue": filtered["days_overdue"],
    "Last Filing":  filtered["last_filing_date"].astype(str),
    "City":         filtered["main_city"].fillna(""),
    "State":        filtered["main_state"].fillna(""),
})

event = st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

selected_rows = event.selection.rows
if selected_rows:
    row = filtered.iloc[selected_rows[0]]
    st.divider()
    st.subheader(row.get("business_name") or row.get("legal_name") or "—")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AUM", fmt_aum(row.get("assets_under_management")))
    c2.metric("Fiscal year end", row.get("fiscal_year_end") or "—")
    c3.metric("Due date", str(row.get("due_date")))
    c4.metric("Days overdue", int(row["days_overdue"]))
    st.markdown(
        f"**Legal name:** {row.get('legal_name') or '—'}  \n"
        f"**Last filing:** {row.get('last_filing_date')}  \n"
        f"**Location:** {row.get('main_city') or '—'}, {row.get('main_state') or '—'}"
    )

# ---------------------------------------------------------------------------
# Overdue by fiscal year end
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Overdue count by fiscal year end")
st.caption("Which annual-amendment waves are being missed. December FYE (due ~March 31) dominates ERA filers.")

by_fye = (
    filtered.groupby("fiscal_year_end", dropna=False)
    .agg(advisers=("entity_key", "nunique"),
         total_aum=("assets_under_management", "sum"))
    .reset_index()
    .sort_values("advisers", ascending=False)
)
st.dataframe(pd.DataFrame({
    "Fiscal year end": by_fye["fiscal_year_end"].fillna("(unknown)"),
    "Advisers":        by_fye["advisers"],
    "Total AUM":       by_fye["total_aum"].apply(fmt_aum),
}), use_container_width=True, hide_index=True)
