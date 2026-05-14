import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import date

from bq import bq_client


def _quarters_ago(n: int) -> pd.Period:
    """Return the Period n quarters before the current quarter."""
    return pd.Timestamp(date.today()).to_period("Q") - n


def _mature_quarters(quarters: list[str], exclude_recent: int = 2) -> list[str]:
    """Return only quarters that are at least exclude_recent quarters old."""
    cutoff = _quarters_ago(exclude_recent)
    result = []
    for q in quarters:
        year, qn = int(q[:4]), int(q[-1])
        if pd.Period(year=year, quarter=qn, freq="Q") <= cutoff:
            result.append(q)
    return result

st.set_page_config(page_title="Nothing Fund Tracker", layout="wide")

st.title("Nothing Fund Tracker")
st.caption(
    "Funds that started with $0 raised, no shared person connections, and first sale yet to occur. "
    "Tracks fundraising velocity ($ per day) broken down by adviser cohort and investor type."
)

COHORT_LABELS = {
    "era_big":           "ERA (Big)",
    "era_small":         "ERA (Small)",
    "multi_state_big":   "Multi-State (Big)",
    "multi_state_small": "Multi-State (Small)",
    "single_state_big":  "Single-State (Big)",
    "single_state_small":"Single-State (Small)",
    "no_adviser":        "No Adviser",
}

INVESTOR_COLORS = {
    "institutional": "#4C72B0",
    "individual":    "#C44E52",
    "other":         "#8C8C8C",
}


def fmt_money(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    if val >= 1_000_000_000:
        return f"${val/1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val/1_000:.0f}K"
    return f"${val:,.0f}"


def fmt_velocity(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M/day"
    if val >= 1_000:
        return f"${val/1_000:.0f}K/day"
    return f"${val:,.0f}/day"


@st.cache_data(ttl=3600)
def load_funds() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            file_num,
            primary_issuer_name,
            primary_issuer_state,
            investment_fund_type,
            investor_type,
            investor_exemption,
            offering_exemption,
            initial_filing_date,
            initial_filing_quarter_label,
            latest_filing_date,
            first_sale_date,
            latest_total_amount_sold,
            has_raised,
            days_since_initial,
            raising_velocity,
            adviser_cohort,
            adviser_aum,
            adviser_legal_name,
            edgar_fund_history_url
        FROM `{project}.sec_filings_marts.form_d_nothing_fund_tracker`
        ORDER BY raising_velocity DESC NULLS LAST
    """).to_dataframe()


df = load_funds()

if df.empty:
    st.warning("No data found.")
    st.stop()

df["cohort_label"] = df["adviser_cohort"].map(COHORT_LABELS).fillna(df["adviser_cohort"])

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    quarters = sorted(df["initial_filing_quarter_label"].dropna().unique())
    mature = _mature_quarters(quarters, exclude_recent=2)
    sel_quarters = st.multiselect(
        "Initial filing quarter",
        options=quarters,
        default=mature,
        help="Most recent 2 quarters excluded by default — those funds haven't had enough time to raise.",
    )

    investor_opts = sorted(df["investor_type"].dropna().unique())
    sel_investor = st.multiselect("Investor type", investor_opts, default=investor_opts)

    fund_types = sorted(df["investment_fund_type"].dropna().unique())
    sel_types = st.multiselect("Fund type", fund_types, default=fund_types)

    only_raised = st.checkbox("Only funds that have raised something", value=False)

filtered = df[
    df["initial_filing_quarter_label"].isin(sel_quarters) &
    df["investor_type"].isin(sel_investor) &
    df["investment_fund_type"].isin(sel_types)
].copy()
if only_raised:
    filtered = filtered[filtered["has_raised"]]

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
raised = filtered[filtered["has_raised"]]
still_zero = filtered[~filtered["has_raised"]]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total nothing funds",  len(filtered))
c2.metric("Have raised",          len(raised))
c3.metric("Still at $0",          len(still_zero))
c4.metric("Median velocity",      fmt_velocity(raised["raising_velocity"].median()))
c5.metric("Median raise",         fmt_money(raised["latest_total_amount_sold"].median()))

st.divider()

# ---------------------------------------------------------------------------
# Velocity by cohort × investor type (institutional vs individual)
# ---------------------------------------------------------------------------
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("Median Velocity by Cohort")
    agg = (
        raised.groupby(["cohort_label", "investor_type"])["raising_velocity"]
        .median()
        .reset_index()
        .rename(columns={"raising_velocity": "median_velocity"})
        .sort_values("median_velocity", ascending=False)
    )
    fig = px.bar(
        agg,
        x="median_velocity",
        y="cohort_label",
        color="investor_type",
        orientation="h",
        barmode="group",
        color_discrete_map=INVESTOR_COLORS,
        labels={
            "median_velocity": "Median Velocity ($/day)",
            "cohort_label":    "",
            "investor_type":   "Investor Type",
        },
    )
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True)

with col_r:
    st.subheader("% Raised by Cohort & Investor Type")
    pct = (
        filtered.groupby(["cohort_label", "investor_type"])
        .agg(total=("file_num", "count"), raised_n=("has_raised", "sum"))
        .reset_index()
    )
    pct["pct_raised"] = (pct["raised_n"] / pct["total"] * 100).round(1)
    fig2 = px.bar(
        pct,
        x="pct_raised",
        y="cohort_label",
        color="investor_type",
        orientation="h",
        barmode="group",
        color_discrete_map=INVESTOR_COLORS,
        labels={
            "pct_raised":   "% of funds that have raised",
            "cohort_label": "",
            "investor_type":"Investor Type",
        },
        text=pct["pct_raised"].apply(lambda x: f"{x:.0f}%"),
    )
    fig2.update_traces(textposition="outside")
    fig2.update_layout(height=420, xaxis_range=[0, 105])
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Fundraising path: cumulative % raised over time by investor type
# ---------------------------------------------------------------------------
st.subheader("Fundraising Path — Cumulative % Raised (Institutional vs Individual)")
st.caption("Shows what % of each cohort had raised money by each day-bucket since their initial filing.")

path_data = raised[raised["investor_type"].isin(["institutional", "individual"])].copy()
if not path_data.empty:
    path_data["days_bucket"] = (path_data["days_since_initial"] // 30 * 30).astype(int)
    total_by_type = filtered[filtered["investor_type"].isin(["institutional", "individual"])].groupby("investor_type")["file_num"].count()

    path_agg = (
        path_data.groupby(["investor_type", "days_bucket"])["file_num"]
        .count()
        .groupby(level=0).cumsum()
        .reset_index()
    )
    path_agg["pct"] = path_agg.apply(
        lambda r: r["file_num"] / total_by_type.get(r["investor_type"], 1) * 100, axis=1
    )
    fig3 = px.line(
        path_agg,
        x="days_bucket",
        y="pct",
        color="investor_type",
        markers=True,
        color_discrete_map=INVESTOR_COLORS,
        labels={
            "days_bucket":   "Days since initial filing",
            "pct":           "% of cohort raised",
            "investor_type": "Investor Type",
        },
    )
    fig3.update_layout(height=380, yaxis_range=[0, 105])
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("Not enough data with current filters.")

st.divider()

# ---------------------------------------------------------------------------
# Scatter: velocity vs amount raised, colored by investor type
# ---------------------------------------------------------------------------
st.subheader("Velocity vs Total Raised")
fig4 = px.scatter(
    raised,
    x="days_since_initial",
    y="latest_total_amount_sold",
    color="investor_type",
    symbol="cohort_label",
    hover_data=["primary_issuer_name", "adviser_legal_name", "investment_fund_type"],
    color_discrete_map=INVESTOR_COLORS,
    log_y=True,
    labels={
        "days_since_initial":         "Days since initial filing",
        "latest_total_amount_sold":   "Total Raised ($)",
        "investor_type":              "Investor Type",
        "cohort_label":               "Adviser Cohort",
    },
)
fig4.update_layout(height=450, yaxis_tickformat="$,.0f")
st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Detail table
# ---------------------------------------------------------------------------
st.subheader("Fund Detail")

display = pd.DataFrame({
    "Fund":           filtered["primary_issuer_name"],
    "Investor Type":  filtered["investor_type"],
    "Cohort":         filtered["cohort_label"],
    "Fund Type":      filtered["investment_fund_type"].fillna("—"),
    "Raised":         filtered["latest_total_amount_sold"].apply(fmt_money),
    "Velocity":       filtered["raising_velocity"].apply(fmt_velocity),
    "Days":           filtered["days_since_initial"].astype("Int64"),
    "Initial Quarter":filtered["initial_filing_quarter_label"],
    "Adviser":        filtered["adviser_legal_name"].fillna("—"),
    "State":          filtered["primary_issuer_state"].fillna("—"),
})

event = st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

selected = event.selection.rows
if selected:
    row = filtered.iloc[selected[0]]
    with st.expander("Detail", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Raised",     fmt_money(row.get("latest_total_amount_sold")))
        c2.metric("Velocity",         fmt_velocity(row.get("raising_velocity")))
        c3.metric("Days to 1st Sale", str(row.get("days_since_initial")) if row.get("has_raised") else f"{row.get('days_since_initial')} (waiting)")
        c4.metric("Date of 1st Sale", str(row.get("first_sale_date")) if row.get("first_sale_date") and str(row.get("first_sale_date")) != "NaT" else "—")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Adviser Cohort", COHORT_LABELS.get(row.get("adviser_cohort"), "—"))
        c6.metric("Adviser AUM",    fmt_money(row.get("adviser_aum")))
        c7.metric("Fund Type",      row.get("investment_fund_type") or "—")
        c8.metric("State",          row.get("primary_issuer_state") or "—")

        if row.get("edgar_fund_history_url"):
            st.link_button("View on EDGAR", row["edgar_fund_history_url"])
