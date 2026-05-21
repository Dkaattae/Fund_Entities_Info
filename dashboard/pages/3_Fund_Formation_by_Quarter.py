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
        WITH us_states AS (
            SELECT s FROM UNNEST([
                'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID',
                'IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS',
                'MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK',
                'OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV',
                'WI','WY','DC'
            ]) AS s
        ),

        -- Priority 1: first Executive Officer or Promoter (by person_seq_key)
        first_officer AS (
            SELECT
                accession_number,
                MIN_BY(state_or_country, person_seq_key) AS person_state
            FROM `{project}.sec_filings_staging.stg_form_d_related_persons`
            WHERE relationship_1 IN ('Executive Officer', 'Promoter')
               OR relationship_2 IN ('Executive Officer', 'Promoter')
            GROUP BY accession_number
        ),

        -- Priority 2: first Director (by person_seq_key)
        first_director AS (
            SELECT
                accession_number,
                MIN_BY(state_or_country, person_seq_key) AS person_state
            FROM `{project}.sec_filings_staging.stg_form_d_related_persons`
            WHERE relationship_1 = 'Director'
               OR relationship_2 = 'Director'
            GROUP BY accession_number
        ),

        funds AS (
            SELECT
                f.accession_number,
                COALESCE(investment_fund_type, 'Unknown') AS fund_type,
                CASE
                    WHEN o.person_state IN (SELECT s FROM us_states)
                        THEN o.person_state
                    WHEN d.person_state IN (SELECT s FROM us_states)
                        THEN d.person_state
                    WHEN f.primary_issuer_state IN (SELECT s FROM us_states)
                        THEN f.primary_issuer_state
                END AS state
            FROM `{project}.sec_filings_marts.form_d_pooled_funds` f
            LEFT JOIN first_officer   o USING (accession_number)
            LEFT JOIN first_director  d USING (accession_number)
            WHERE f.is_amendment_submission = false
              AND f.filing_date >= '2025-04-01'
              AND LOWER(f.primary_issuer_name) NOT LIKE '%a series of%'
        )

        SELECT state, fund_type, COUNT(*) AS fund_count
        FROM funds
        WHERE state IS NOT NULL
        GROUP BY state, fund_type
        ORDER BY fund_count DESC
    """).to_dataframe()


@st.cache_data(ttl=3600)
def load_platform_funds() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            FORMAT_DATE('%Y-Q%Q', filing_date)              AS quarter_label,
            COALESCE(investment_fund_type, 'Unknown')        AS fund_type,
            COUNT(*)                                         AS fund_count
        FROM `{project}.sec_filings_marts.form_d_pooled_funds`
        WHERE is_amendment_submission = false
          AND filing_date >= '2025-04-01'
          AND LOWER(primary_issuer_name) LIKE '%a series of%'
        GROUP BY quarter_label, fund_type
        ORDER BY quarter_label, fund_type
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
st.caption(
    "Location = first Executive Officer or Promoter's state from Form D related persons; "
    "falls back to issuer's principal place of business. "
    "WA is inflated by AngelList/Roll-Up series funds whose Form D only lists a Lynnwood registered agent."
)

state_df_raw = load_state_map()
state_df = (
    state_df_raw[state_df_raw["fund_type"].isin(selected_types)]
    .groupby("state", as_index=False)["fund_count"].sum()
    .sort_values("fund_count", ascending=False)
)

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

st.divider()

# ---------------------------------------------------------------------------
# Platform / Syndicate Funds (AngelList-type "a series of X")
# ---------------------------------------------------------------------------
st.subheader("Platform / Syndicate Funds")
st.caption(
    'Funds whose name contains "a series of" — AngelList syndicates and similar '
    "back-office platforms (e.g. Belltower Fund Group, CGF2021). "
    "Excluded from the state map above as their registered address does not "
    "reflect the manager's actual location."
)

platform_df = load_platform_funds()

if not platform_df.empty:
    platform_df["_shared_bucket"] = platform_df.get("_shared_bucket", None)

    # Apply same fund type filter
    platform_filtered = platform_df[platform_df["fund_type"].isin(selected_types)]

    by_q = platform_filtered.groupby("quarter_label")["fund_count"].sum().reset_index()

    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Total platform funds (period)", int(platform_filtered["fund_count"].sum()))
    col_m2.metric("Latest full quarter (2026-Q1)",
                  int(platform_filtered[platform_filtered["quarter_label"] == "2026-Q1"]["fund_count"].sum()))

    fig_platform = px.bar(
        platform_filtered,
        x="quarter_label",
        y="fund_count",
        color="fund_type",
        barmode="stack",
        text_auto=True,
        labels={"quarter_label": "Quarter", "fund_count": "Platform Funds", "fund_type": "Fund Type"},
    )
    fig_platform.update_layout(xaxis_title=None, yaxis_title="Platform Funds", height=380)
    st.plotly_chart(fig_platform, use_container_width=True)
