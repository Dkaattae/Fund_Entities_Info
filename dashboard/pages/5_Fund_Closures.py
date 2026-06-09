import pandas as pd
import plotly.express as px
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Fund Closures", layout="wide")

st.title("Fund Closures")
st.caption(
    "ERA (Form ADV) closure signals. "
    "final_filing: adviser filed an SEC/state final filing (authoritative). "
    "fund_removed: a specific fund dropped from Form ADV year-over-year. "
    "aum_zeroed: adviser AUM went from > 0 to a reported 0."
)
st.caption(
    "⏱ Timing note: events are bucketed by the **calendar quarter the filing was submitted**, "
    "not by fiscal year. A *final_filing* is dated when the adviser actually withdrew. "
    "*fund_removed* / *aum_zeroed* are year-over-year (fiscal) signals, so an FY2025 event "
    "appears in the quarter that year's annual amendment was filed — typically early 2026."
)

SIGNAL_LABELS = {
    "final_filing": "Final Filing",
    "fund_removed": "Fund Removed from ADV",
    "aum_zeroed":   "AUM Dropped to Zero",
}


def fmt_aum(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    if val >= 1_000_000_000:
        return f"${val/1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val/1_000:.0f}K"
    return f"${val:,.0f}"


@st.cache_data(ttl=3600)
def load_closures() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            entity_key,
            legal_name,
            business_name,
            main_city,
            main_state,
            iapd_url,
            closure_signal,
            filing_date_current,
            filing_date_prior,
            days_since_prior_filing,
            is_late_filer,
            closure_quarter_label,
            form_d_file_number,
            fund_name,
            edgar_fund_history_url,
            current_aum,
            prior_aum
        FROM `{project}.sec_filings_marts.era_fund_closures`
        ORDER BY filing_date_current DESC
    """).to_dataframe()


df = load_closures()

if df.empty:
    st.warning("No closure events found.")
    st.stop()

df["signal_label"] = df["closure_signal"].map(SIGNAL_LABELS).fillna(df["closure_signal"])

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    signal_options = list(SIGNAL_LABELS.keys())
    selected_signals = st.multiselect(
        "Closure signal",
        signal_options,
        default=signal_options,
        format_func=lambda x: SIGNAL_LABELS[x],
    )

    quarters = sorted(df["closure_quarter_label"].dropna().unique())
    selected_quarters = st.multiselect("Filed Quarter", quarters, default=quarters)

    st.divider()
    hide_late_filers = st.checkbox(
        "Hide late filers (>18 months gap)",
        value=False,
        help=(
            "Late filers filed their annual amendment more than 18 months after their previous one. "
            "Their closure may have occurred much earlier than the Q1 spike suggests."
        ),
    )

filtered = df[
    df["closure_signal"].isin(selected_signals) &
    df["closure_quarter_label"].isin(selected_quarters)
].copy()

if hide_late_filers:
    filtered = filtered[~filtered["is_late_filer"].fillna(False)]

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
late_filer_count = int(filtered["is_late_filer"].fillna(False).sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total closure events", len(filtered))
c2.metric("Final filings",        int((filtered["closure_signal"] == "final_filing").sum()))
c3.metric("Fund removed events",  int((filtered["closure_signal"] == "fund_removed").sum()))
c4.metric("AUM zeroed events",    int((filtered["closure_signal"] == "aum_zeroed").sum()))
c5.metric("Late filers (>18 mo)", late_filer_count,
          help="Advisers whose prior annual amendment was filed more than 18 months earlier. "
               "Their detected closure date may lag the actual closure by a year or more.")

st.divider()

# ---------------------------------------------------------------------------
# Bar chart: closures by quarter, broken down by signal type
# ---------------------------------------------------------------------------
st.subheader("Closure Events by Filed Quarter")
st.caption("X-axis = calendar quarter the filing was submitted (not fiscal year). See timing note above.")

by_quarter = (
    filtered.groupby(["closure_quarter_label", "signal_label"])
    .size()
    .reset_index(name="count")
)

fig = px.bar(
    by_quarter,
    x="closure_quarter_label",
    y="count",
    color="signal_label",
    barmode="stack",
    labels={
        "closure_quarter_label": "Filed Quarter",
        "count":                 "Events",
        "signal_label":          "Signal",
    },
    text_auto=True,
)
fig.update_layout(xaxis_title=None, yaxis_title="Closure Events", height=400)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Detail table
# ---------------------------------------------------------------------------
st.subheader("Closure Events")

display = pd.DataFrame({
    "Adviser":            filtered["business_name"].fillna(filtered["legal_name"]),
    "Signal":             filtered["signal_label"],
    "Detected":           filtered["filing_date_current"].astype(str),
    "Prior Filing":       filtered["filing_date_prior"].astype(str),
    "Days Since Prior":   filtered["days_since_prior_filing"].apply(
                              lambda v: f"{int(v):,}" if pd.notna(v) else "—"
                          ),
    "Late Filer":         filtered["is_late_filer"].apply(
                              lambda v: "⚠ Yes" if v else ""
                          ),
    "Filed Quarter":      filtered["closure_quarter_label"],
    "Fund":               filtered["fund_name"].fillna("—"),
    "File No.":           filtered["form_d_file_number"].fillna("—"),
    "AUM Before":         filtered["prior_aum"].apply(fmt_aum),
    "AUM After":          filtered["current_aum"].apply(fmt_aum),
    "City":               filtered["main_city"].fillna(""),
    "State":              filtered["main_state"].fillna(""),
})

event = st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ---------------------------------------------------------------------------
# Detail panel
# ---------------------------------------------------------------------------
selected = event.selection.rows
if selected:
    row = filtered.iloc[selected[0]]
    st.divider()
    adviser_name = row.get("business_name") or row.get("legal_name") or "—"
    st.subheader(adviser_name)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Signal",       SIGNAL_LABELS.get(row.get("closure_signal"), "—"))
    c2.metric("Detected",     str(row.get("filing_date_current")))
    c3.metric("AUM Before",   fmt_aum(row.get("prior_aum")))
    c4.metric("AUM After",    fmt_aum(row.get("current_aum")))

    if row.get("fund_name"):
        st.markdown(f"**Fund:** {row['fund_name']}  |  **File No.:** {row.get('form_d_file_number') or '—'}")

    link_col1, link_col2 = st.columns(2)
    if row.get("iapd_url"):
        link_col1.link_button("View adviser on IAPD", row["iapd_url"])
    if row.get("edgar_fund_history_url"):
        link_col2.link_button("View fund on EDGAR", row["edgar_fund_history_url"])
