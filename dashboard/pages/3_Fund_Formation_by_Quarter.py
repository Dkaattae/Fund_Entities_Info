import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Fund Formation by Quarter", layout="wide")

st.title("Fund Formation by Quarter")
st.caption("Initial (non-amendment) Form D filings for pooled investment funds — 2024 onward")

FUND_TYPE_ORDER = [
    "Hedge Fund",
    "Private Equity Fund",
    "Venture Capital Fund",
    "Real Estate Fund",
    "Other Investment Fund",
    "Unknown",
]


@st.cache_data(ttl=3600)
def load_by_quarter() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT quarter_label, fund_type, fund_count
        FROM `{project}.sec_filings_marts.form_d_new_funds_by_quarter`
        ORDER BY filing_quarter, fund_type
    """).to_dataframe()


@st.cache_data(ttl=3600)
def load_state_map() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            primary_issuer_state   AS state,
            COUNT(*)               AS fund_count
        FROM `{project}.sec_filings_marts.form_d_pooled_funds`
        WHERE is_amendment_submission = false
          AND filing_date >= '2025-04-01'
          AND primary_issuer_state IS NOT NULL
          AND primary_issuer_state NOT LIKE 'X%'
        GROUP BY state
        ORDER BY fund_count DESC
    """).to_dataframe()


df = load_by_quarter()

if df.empty:
    st.warning("No data found. Run the dbt model form_d_new_funds_by_quarter first.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    all_types = FUND_TYPE_ORDER + [t for t in df["fund_type"].unique() if t not in FUND_TYPE_ORDER]
    selected_types = st.multiselect("Fund Type", all_types, default=all_types)

filtered = df[df["fund_type"].isin(selected_types)]

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
total = filtered["fund_count"].sum()
quarters = filtered["quarter_label"].nunique()
by_q = filtered.groupby("quarter_label")["fund_count"].sum()

c1, c2, c3 = st.columns(3)
c1.metric("Total funds formed", int(total))
c2.metric("Quarters shown", quarters)
c3.metric("Avg per quarter", f"{by_q.mean():.0f}" if quarters else "—")

st.divider()

# ---------------------------------------------------------------------------
# Stacked bar: fund count by quarter, broken down by fund type
# ---------------------------------------------------------------------------
st.subheader("New Fund Filings per Quarter by Type")

# Order fund types consistently
type_order = [t for t in FUND_TYPE_ORDER if t in filtered["fund_type"].unique()]
type_order += [t for t in filtered["fund_type"].unique() if t not in type_order]

fig = px.bar(
    filtered,
    x="quarter_label",
    y="fund_count",
    color="fund_type",
    category_orders={"fund_type": type_order},
    labels={
        "quarter_label": "Quarter",
        "fund_count":    "New Funds",
        "fund_type":     "Fund Type",
    },
    barmode="stack",
    text_auto=True,
)
fig.update_layout(
    xaxis_title=None,
    yaxis_title="New Funds",
    legend_title="Fund Type",
    height=480,
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Trend lines per fund type
# ---------------------------------------------------------------------------
st.subheader("Trend by Fund Type")

fig_line = px.line(
    filtered,
    x="quarter_label",
    y="fund_count",
    color="fund_type",
    markers=True,
    category_orders={"fund_type": type_order},
    labels={
        "quarter_label": "Quarter",
        "fund_count":    "New Funds",
        "fund_type":     "Fund Type",
    },
)
fig_line.update_layout(xaxis_title=None, yaxis_title="New Funds", height=380)
st.plotly_chart(fig_line, use_container_width=True)

# ---------------------------------------------------------------------------
# Raw table
# ---------------------------------------------------------------------------
with st.expander("Raw data"):
    pivot = filtered.pivot_table(
        index="quarter_label", columns="fund_type", values="fund_count", fill_value=0
    ).reset_index()
    pivot["Total"] = pivot.drop(columns="quarter_label").sum(axis=1)
    st.dataframe(pivot, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# US state heatmap — 2025 Q2 through current (includes Form D daily data)
# ---------------------------------------------------------------------------
st.subheader("Fund Formation by State")
st.caption("US-only initial Form D filings from 2025-Q2 onward, including Form D daily data.")

state_df = load_state_map()

if state_df.empty:
    st.info("No state data available.")
else:
    fig_map = px.choropleth(
        state_df,
        locations="state",
        locationmode="USA-states",
        color="fund_count",
        scope="usa",
        color_continuous_scale="Blues",
        labels={"fund_count": "New Funds", "state": "State"},
        hover_data={"state": True, "fund_count": True},
    )
    fig_map.update_layout(
        height=500,
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar=dict(title="New Funds"),
    )
    st.plotly_chart(fig_map, use_container_width=True)

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Top 10 States")
        st.dataframe(
            state_df.head(10).rename(columns={"state": "State", "fund_count": "New Funds"}),
            use_container_width=True,
            hide_index=True,
        )
    with col_r:
        fig_bar = px.bar(
            state_df.head(15).sort_values("fund_count"),
            x="fund_count",
            y="state",
            orientation="h",
            labels={"fund_count": "New Funds", "state": ""},
            color="fund_count",
            color_continuous_scale="Blues",
            title="Top 15 States",
        )
        fig_bar.update_layout(height=420, showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig_bar, use_container_width=True)
