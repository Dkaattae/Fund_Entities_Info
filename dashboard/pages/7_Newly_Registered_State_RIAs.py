import altair as alt
import pandas as pd
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Newly Registered State RIAs", layout="wide")

st.title("Newly Registered State RIAs")
st.caption(
    "Investment advisers registered at the state level (STATE registrations, not SEC ERA). "
    "Data sourced from the SEC IA_FIRM_STATE feed, updated daily."
)

AUM_BUCKET_ORDER = ["No AUM", "<$1M", "$1M–$10M", "$10M–$100M", "$100M+"]


def aum_bucket(aum) -> str:
    if pd.isna(aum) or aum == 0:
        return "No AUM"
    if aum < 1_000_000:
        return "<$1M"
    if aum < 10_000_000:
        return "$1M–$10M"
    if aum < 100_000_000:
        return "$10M–$100M"
    return "$100M+"


def fmt_aum(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    return f"${val:,.0f}"


@st.cache_data(ttl=3600)
def load_state_rias() -> pd.DataFrame:
    client, project = bq_client()
    query = f"""
        WITH state_firms AS (
            -- One row per firm that has at least one STATE registration.
            -- Firm-level count columns are identical across all rows for the
            -- same firm so any_value is safe here.
            SELECT
                firm_crd,
                ANY_VALUE(state_registration_count) AS state_registration_count,
                ANY_VALUE(era_registration_count)   AS era_registration_count,
                ANY_VALUE(total_jurisdiction_count) AS total_jurisdiction_count
            FROM `{project}.sec_filings_marts.ria_state_registrations`
            WHERE registration_type = 'STATE'
            GROUP BY firm_crd
        )
        SELECT
            n.firm_crd,
            COALESCE(n.business_name, n.legal_name) AS firm_name,
            n.main_state,
            n.main_city,
            n.aum_total,
            n.aum_discretionary,
            n.total_employees,
            n.status,
            n.first_seen_date,
            n.last_observed_date,
            s.state_registration_count,
            s.era_registration_count,
            s.total_jurisdiction_count
        FROM `{project}.sec_filings_marts.newly_registered_rias` n
        INNER JOIN state_firms s USING (firm_crd)
        ORDER BY n.first_seen_date DESC
    """
    df = client.query(query).to_dataframe()
    # Normalize types: BQ returns Int64 (nullable) and dbdate — convert explicitly
    df["first_seen_date"] = pd.to_datetime(df["first_seen_date"].astype(str), errors="coerce")
    df["last_observed_date"] = pd.to_datetime(df["last_observed_date"].astype(str), errors="coerce")
    df["aum_total"] = pd.to_numeric(df["aum_total"], errors="coerce")
    df["aum_discretionary"] = pd.to_numeric(df["aum_discretionary"], errors="coerce")
    for col in ["total_employees", "state_registration_count", "era_registration_count", "total_jurisdiction_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["aum_bucket"] = df["aum_total"].apply(aum_bucket)
    return df


df = load_state_rias()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    lookback_options = {"Last 30 days": 30, "Last 90 days": 90, "Last 180 days": 180, "All time": None}
    lookback_label = st.selectbox("First registered", list(lookback_options.keys()), index=1)
    lookback_days = lookback_options[lookback_label]

    state_options = sorted(df["main_state"].dropna().unique().tolist())
    selected_states = st.multiselect("HQ state", state_options, default=[])

    status_options = sorted(df["status"].dropna().unique().tolist())
    selected_status = st.multiselect("Status", status_options, default=status_options)

# Apply filters
filtered = df.copy()
if lookback_days is not None:
    cutoff = pd.Timestamp.now(tz=None) - pd.Timedelta(days=lookback_days)
    filtered = filtered[filtered["first_seen_date"] >= cutoff]
if selected_states:
    filtered = filtered[filtered["main_state"].isin(selected_states)]
if selected_status:
    filtered = filtered[filtered["status"].isin(selected_status)]

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Firms", len(filtered))
c2.metric("With AUM reported", int(filtered["aum_total"].notna().sum()))
median_aum = filtered["aum_total"].dropna()
c3.metric("Median AUM", fmt_aum(median_aum.median()) if len(median_aum) else "—")
c4.metric("Avg state registrations", f"{filtered['state_registration_count'].mean():.1f}" if len(filtered) else "—")

st.divider()

# ---------------------------------------------------------------------------
# AUM cohort bar chart
# ---------------------------------------------------------------------------
st.subheader("AUM Cohort Distribution")

bucket_counts = (
    filtered["aum_bucket"]
    .value_counts()
    .reindex(AUM_BUCKET_ORDER, fill_value=0)
    .reset_index()
    .rename(columns={"index": "AUM Range", "aum_bucket": "Firms", "count": "Firms"})
)
# Altair expects the column names from the actual DataFrame
bucket_counts.columns = ["AUM Range", "Firms"]
bucket_counts["AUM Range"] = pd.Categorical(bucket_counts["AUM Range"], categories=AUM_BUCKET_ORDER, ordered=True)

chart = (
    alt.Chart(bucket_counts)
    .mark_bar(color="#4C78A8")
    .encode(
        x=alt.X("AUM Range:O", sort=AUM_BUCKET_ORDER, title="AUM Range"),
        y=alt.Y("Firms:Q", title="Number of Firms"),
        tooltip=["AUM Range", "Firms"],
    )
    .properties(height=280)
)
st.altair_chart(chart, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Firm table
# ---------------------------------------------------------------------------
st.subheader("Firm List")

display = pd.DataFrame({
    "Firm":             filtered["firm_name"],
    "HQ State":         filtered["main_state"].fillna(""),
    "HQ City":          filtered["main_city"].fillna(""),
    "AUM":              filtered["aum_total"].apply(fmt_aum),
    "AUM Bucket":       filtered["aum_bucket"],
    "Employees":        filtered["total_employees"].apply(lambda x: "" if pd.isna(x) else str(int(x))),
    "State Regs":       filtered["state_registration_count"].fillna(0).astype(int),
    "ERA Regs":         filtered["era_registration_count"].fillna(0).astype(int),
    "First Seen":       filtered["first_seen_date"].dt.strftime("%Y-%m-%d").fillna(""),
    "Status":           filtered["status"].fillna(""),
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
    st.subheader(row["firm_name"])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("AUM (Total)",         fmt_aum(row.get("aum_total")))
    col2.metric("AUM (Discretionary)", fmt_aum(row.get("aum_discretionary")))
    col3.metric("Total Employees",     str(int(row["total_employees"])) if pd.notna(row.get("total_employees")) else "—")
    col4.metric("Status",              row.get("status") or "—")
    col1b, col2b, col3b = st.columns(3)
    col1b.metric("First Seen",           str(row["first_seen_date"].date()) if pd.notna(row.get("first_seen_date")) else "—")
    col2b.metric("Last Observed",        str(row["last_observed_date"].date()) if pd.notna(row.get("last_observed_date")) else "—")
    col3b.metric("State Registrations",  str(int(row["state_registration_count"])) if pd.notna(row.get("state_registration_count")) else "—")
    st.caption(f"CRD: {row['firm_crd']}  |  HQ: {row.get('main_city') or ''}, {row.get('main_state') or ''}")
