import pandas as pd
import plotly.express as px
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="First Round Fundraise", layout="wide")

st.title("First Round Fundraise")
st.caption(
    "Form D pooled investment funds — first time total_amount_sold > 0, "
    "grouped by adviser cohort and fund characteristics. 2024 onward."
)

COHORT_ORDER = [
    "era_big", "era_small",
    "multi_state_big", "multi_state_small",
    "single_state_big", "single_state_small",
    "no_adviser",
]

COHORT_LABELS = {
    "era_big":           "ERA (Big)",
    "era_small":         "ERA (Small)",
    "multi_state_big":   "Multi-State (Big)",
    "multi_state_small": "Multi-State (Small)",
    "single_state_big":  "Single-State (Big)",
    "single_state_small":"Single-State (Small)",
    "no_adviser":        "No Adviser",
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
def load_first_raise() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            file_num,
            primary_issuer_name,
            primary_issuer_state,
            entity_type,
            investment_fund_type,
            investor_exemption,
            offering_exemption,
            initial_filing_date,
            initial_filing_quarter_label,
            first_raise_date,
            first_raise_amount,
            days_to_first_raise,
            manager_type,
            adviser_cohort,
            adviser_aum,
            adviser_state_registration_count,
            adviser_legal_name,
            shared_fund_count
        FROM `{project}.sec_filings_marts.form_d_first_raise`
        ORDER BY first_raise_amount DESC NULLS LAST
    """).to_dataframe()


SHARED_CONN_LABELS = ["0", "1–10", "10–30", "30+"]

def _shared_conn_bucket(n) -> str:
    if pd.isna(n) or n == 0:
        return "0"
    if n <= 10:
        return "1–10"
    if n <= 30:
        return "10–30"
    return "30+"


df = load_first_raise()

if df.empty:
    st.warning("No data found. Run the dbt model form_d_first_raise first.")
    st.stop()

df["adviser_cohort_label"] = df["adviser_cohort"].map(COHORT_LABELS).fillna(df["adviser_cohort"])
df["_shared_bucket"] = df["shared_fund_count"].apply(_shared_conn_bucket)
df["_is_us"] = ~df["primary_issuer_state"].fillna("X").str.startswith("X")
df["display_fund_type"] = df["primary_issuer_name"].str.lower().str.contains(
    "a series of", na=False
).map({True: "Platform / Syndicate", False: None}).fillna(df["investment_fund_type"])

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    location_filter = st.radio(
        "Fund Location",
        options=["All", "US only", "Non-US only"],
        index=0,
    )

    selected_buckets = st.multiselect(
        "Shared Connections",
        SHARED_CONN_LABELS,
        default=SHARED_CONN_LABELS,
    )

    fund_types = sorted(df["display_fund_type"].dropna().unique())
    selected_types = st.multiselect("Fund Type", fund_types, default=fund_types)

    max_days = int(df["days_to_first_raise"].max()) if df["days_to_first_raise"].notna().any() else 365
    days_range = st.slider("Max days to first raise", 0, max_days, max_days)

    st.divider()
    exclude_large = st.checkbox(
        "Exclude raises > $100M",
        value=True,
        help="Funds raising over $100M are typically SEC-registered RIAs, not ERA filers.",
    )

location_mask = (
    df["_is_us"] if location_filter == "US only" else
    ~df["_is_us"] if location_filter == "Non-US only" else
    pd.Series(True, index=df.index)
)

filtered = df[
    location_mask &
    df["_shared_bucket"].isin(selected_buckets) &
    df["display_fund_type"].isin(selected_types) &
    (df["days_to_first_raise"] <= days_range)
].copy()

if exclude_large:
    filtered = filtered[filtered["first_raise_amount"] <= 100_000_000]

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Funds with first raise", len(filtered))
c2.metric("Median raise", fmt_aum(filtered["first_raise_amount"].median()))
c3.metric("Total raised", fmt_aum(filtered["first_raise_amount"].sum()))
c4.metric("Median days to raise", f"{filtered['days_to_first_raise'].median():.0f}")

st.divider()

# ---------------------------------------------------------------------------
# Median raise by adviser cohort
# ---------------------------------------------------------------------------
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Median First Raise by Adviser Cohort")
    cohort_agg = (
        filtered.groupby("adviser_cohort_label")["first_raise_amount"]
        .agg(median="median", count="count")
        .reset_index()
        .sort_values("median", ascending=False)
    )
    fig_cohort = px.bar(
        cohort_agg,
        x="median",
        y="adviser_cohort_label",
        orientation="h",
        text=cohort_agg["median"].apply(fmt_aum),
        labels={"median": "Median First Raise", "adviser_cohort_label": ""},
        hover_data={"count": True},
        color_discrete_sequence=["#4C72B0"],
    )
    fig_cohort.update_traces(textposition="outside")
    fig_cohort.update_layout(height=380, xaxis_tickformat="$,.0f")
    st.plotly_chart(fig_cohort, use_container_width=True)

# ---------------------------------------------------------------------------
# Median days to first raise by cohort
# ---------------------------------------------------------------------------
with col_right:
    st.subheader("Median Days to First Raise by Cohort")
    days_agg = (
        filtered.groupby("adviser_cohort_label")["days_to_first_raise"]
        .median()
        .reset_index()
        .rename(columns={"days_to_first_raise": "median_days"})
        .sort_values("median_days")
    )
    fig_days = px.bar(
        days_agg,
        x="median_days",
        y="adviser_cohort_label",
        orientation="h",
        text=days_agg["median_days"].apply(lambda x: f"{x:.0f} days"),
        labels={"median_days": "Median Days", "adviser_cohort_label": ""},
        color_discrete_sequence=["#55A868"],
    )
    fig_days.update_traces(textposition="outside")
    fig_days.update_layout(height=380)
    st.plotly_chart(fig_days, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Breakdown by fund type and exemption
# ---------------------------------------------------------------------------
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("Median Raise by Fund Type")
    type_agg = (
        filtered.groupby("display_fund_type")["first_raise_amount"]
        .agg(median="median", count="count")
        .reset_index()
        .rename(columns={"display_fund_type": "investment_fund_type"})
        .sort_values("median", ascending=False)
    )
    fig_type = px.bar(
        type_agg,
        x="investment_fund_type",
        y="median",
        text=type_agg["median"].apply(fmt_aum),
        labels={"investment_fund_type": "", "median": "Median First Raise"},
        color_discrete_sequence=["#C44E52"],
    )
    fig_type.update_traces(textposition="outside")
    fig_type.update_layout(height=360, yaxis_tickformat="$,.0f")
    st.plotly_chart(fig_type, use_container_width=True)

with col_r:
    st.subheader("Median Raise by Investor Exemption")
    exemp_agg = (
        filtered.groupby("investor_exemption")["first_raise_amount"]
        .agg(median="median", count="count")
        .reset_index()
        .sort_values("median", ascending=False)
    )
    fig_exemp = px.bar(
        exemp_agg,
        x="investor_exemption",
        y="median",
        text=exemp_agg["median"].apply(fmt_aum),
        labels={"investor_exemption": "", "median": "Median First Raise"},
        color_discrete_sequence=["#8172B2"],
    )
    fig_exemp.update_traces(textposition="outside")
    fig_exemp.update_layout(height=360, yaxis_tickformat="$,.0f")
    st.plotly_chart(fig_exemp, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Scatter: raise amount vs days to raise
# ---------------------------------------------------------------------------
st.subheader("Raise Amount vs Days to First Raise")
fig_scatter = px.scatter(
    filtered,
    x="days_to_first_raise",
    y="first_raise_amount",
    color="adviser_cohort_label",
    hover_data=["primary_issuer_name", "investment_fund_type", "adviser_legal_name"],
    labels={
        "days_to_first_raise":  "Days to First Raise",
        "first_raise_amount":   "First Raise Amount ($)",
        "adviser_cohort_label": "Adviser Cohort",
    },
    log_y=True,
)
fig_scatter.update_layout(height=450, yaxis_tickformat="$,.0f")
st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Top raises table
# ---------------------------------------------------------------------------
st.subheader("Top Raises")

display = pd.DataFrame({
    "Fund":               filtered["primary_issuer_name"],
    "First Raise":        filtered["first_raise_amount"].apply(fmt_aum),
    "Days to Raise":      filtered["days_to_first_raise"].astype("Int64"),
    "Shared Connections": filtered["shared_fund_count"].astype("Int64"),
    "Fund Type":          filtered["display_fund_type"].fillna("—"),
    "Investor Exempt.":   filtered["investor_exemption"],
    "Offering Exempt.":   filtered["offering_exemption"],
    "Adviser Cohort":     filtered["adviser_cohort_label"],
    "Adviser":            filtered["adviser_legal_name"].fillna("—"),
    "Quarter":            filtered["initial_filing_quarter_label"],
    "State":              filtered["primary_issuer_state"].fillna("—"),
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
        c1.metric("First Raise", fmt_aum(row.get("first_raise_amount")))
        c2.metric("Days to Raise", f"{row.get('days_to_first_raise'):.0f}")
        c3.metric("Initial Filing", str(row.get("initial_filing_date")))
        c4.metric("First Raise Date", str(row.get("first_raise_date")))

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Adviser", row.get("adviser_legal_name") or "—")
        c6.metric("Adviser Cohort", COHORT_LABELS.get(row.get("adviser_cohort"), "—"))
        c7.metric("Adviser AUM", fmt_aum(row.get("adviser_aum")))
        c8.metric("State Registrations",
                  str(int(row["adviser_state_registration_count"]))
                  if pd.notna(row.get("adviser_state_registration_count")) else "—")
