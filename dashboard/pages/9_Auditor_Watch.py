import pandas as pd
import streamlit as st

from bq import bq_client, run_query

st.set_page_config(page_title="Auditor Watch", layout="wide")

st.title("Auditor Watch — Non-PCAOB Auditors")
st.caption(
    "ERA advisers whose latest Form ADV reports fund auditors that are not PCAOB-registered "
    "(or registered but not subject to inspection). As private-fund AUM approaches SEC-registration "
    "territory (~$150M), the custody rule effectively requires a PCAOB-registered and inspected "
    "auditor — these advisers are either future auditor-upgrade leads, winding down, staying exempt, "
    "or fraud signals. Template clusters (many advisers sharing one auditor and one identical AUM) "
    "are flagged separately."
)

STATUS_LABELS = {
    "no_pcaob_auditor":         "No PCAOB auditor",
    "mixed":                    "Mixed (some non-PCAOB)",
    "registered_not_inspected": "PCAOB registered, not inspected",
    "pcaob_inspected":          "PCAOB registered + inspected",
}
LEAD_STATUSES = ["no_pcaob_auditor", "mixed", "registered_not_inspected"]
AUM_BUCKETS = [">= $1B", "$150M - $1B", "< $150M", "unknown"]
TEMPLATE_PEER_THRESHOLD = 5


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
def load_advisers() -> pd.DataFrame:
    _, project = bq_client()
    df = run_query(f"""
        SELECT
            entity_key, legal_name, business_name, main_city, main_state,
            main_country, assets_under_management, aum_bucket, auditor_status,
            auditor_count, auditor_names, non_pcaob_auditor_names,
            auditor_countries, same_auditor_same_aum_advisers,
            latest_filing_date, fiscal_year, iapd_url
        FROM `{project}.sec_filings_marts.adviser_auditor_status`
        ORDER BY assets_under_management DESC NULLS LAST
    """)
    df["assets_under_management"] = pd.to_numeric(df["assets_under_management"], errors="coerce")
    df["same_auditor_same_aum_advisers"] = pd.to_numeric(
        df["same_auditor_same_aum_advisers"], errors="coerce").fillna(1).astype(int)
    return df


df = load_advisers()
df["is_template_cluster"] = df["same_auditor_same_aum_advisers"] >= TEMPLATE_PEER_THRESHOLD

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    selected_statuses = st.multiselect(
        "Auditor status",
        options=list(STATUS_LABELS.keys()),
        default=LEAD_STATUSES,
        format_func=lambda s: STATUS_LABELS[s],
    )
    selected_buckets = st.multiselect("AUM bucket", AUM_BUCKETS, default=AUM_BUCKETS)
    hide_templates = st.toggle(
        "Hide likely template/fraud clusters",
        value=True,
        help=f"Excludes advisers sharing one auditor and one identical AUM with "
             f">= {TEMPLATE_PEER_THRESHOLD} peers. They are shown in their own section below.",
    )

filtered = df.copy()
if selected_statuses:
    filtered = filtered[filtered["auditor_status"].isin(selected_statuses)]
if selected_buckets:
    filtered = filtered[filtered["aum_bucket"].isin(selected_buckets)]
if hide_templates:
    filtered = filtered[~filtered["is_template_cluster"]]

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
leads = df[df["auditor_status"].isin(LEAD_STATUSES) & ~df["is_template_cluster"]]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Non-PCAOB / partial advisers", f"{len(leads):,}")
col2.metric("of which AUM ≥ $150M", f"{(leads['aum_bucket'].isin(['>= $1B', '$150M - $1B'])).sum():,}")
col3.metric("Template-cluster filers", f"{df['is_template_cluster'].sum():,}")
col4.metric(
    "Distinct non-PCAOB auditor firms",
    f"{leads['non_pcaob_auditor_names'].dropna().str.split('; ').explode().nunique():,}",
)

# ---------------------------------------------------------------------------
# Lead table
# ---------------------------------------------------------------------------
st.subheader(f"Advisers ({len(filtered):,})")

display = pd.DataFrame({
    "Adviser":            filtered["legal_name"].fillna(""),
    "City":               filtered["main_city"].fillna(""),
    "State":              filtered["main_state"].fillna(""),
    "Country":            filtered["main_country"].fillna(""),
    "AUM":                filtered["assets_under_management"].apply(fmt_aum),
    "Bucket":             filtered["aum_bucket"],
    "Status":             filtered["auditor_status"].map(STATUS_LABELS),
    "Non-PCAOB auditors": filtered["non_pcaob_auditor_names"].fillna(""),
    "Same-AUM peers":     filtered["same_auditor_same_aum_advisers"],
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
    st.subheader(row["legal_name"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AUM", fmt_aum(row.get("assets_under_management")))
    c2.metric("Auditor status", STATUS_LABELS.get(row["auditor_status"], row["auditor_status"]))
    c3.metric("Auditors on filing", int(row["auditor_count"]))
    c4.metric("Same-auditor same-AUM peers", int(row["same_auditor_same_aum_advisers"]))

    st.markdown(f"**Auditors:** {row.get('auditor_names') or '—'}")
    st.markdown(f"**Auditor countries:** {row.get('auditor_countries') or '—'}")
    if pd.notna(row.get("iapd_url")) and row.get("iapd_url"):
        st.markdown(f"[View on IAPD]({row['iapd_url']})")

# ---------------------------------------------------------------------------
# Template clusters (fraud signal)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Suspicious template clusters")
st.caption(
    "Groups of advisers reporting the same auditor AND the exact same AUM — legitimate books "
    "rarely collide to the dollar. Example: 98 filers, all audited by INDICATOR GLOBAL, all "
    "reporting exactly $80M, with exchange/forex/AI-themed names and impersonations of real firms."
)

tpl = df[df["is_template_cluster"]]
if tpl.empty:
    st.info("No template clusters at the current threshold.")
else:
    clusters = (
        tpl.groupby(["non_pcaob_auditor_names", "assets_under_management"], dropna=False)
        .agg(advisers=("entity_key", "nunique"),
             sample_names=("legal_name", lambda s: "; ".join(s.head(5))))
        .reset_index()
        .sort_values("advisers", ascending=False)
    )
    st.dataframe(pd.DataFrame({
        "Auditor":       clusters["non_pcaob_auditor_names"].fillna("(PCAOB-registered auditor)"),
        "Reported AUM":  clusters["assets_under_management"].apply(fmt_aum),
        "Advisers":      clusters["advisers"],
        "Sample names":  clusters["sample_names"],
    }), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Top non-PCAOB auditor firms
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Top non-PCAOB auditor firms")
st.caption("By count of advisers using them on their latest filing (template clusters excluded).")

firms = (
    leads.dropna(subset=["non_pcaob_auditor_names"])
    .assign(firm=lambda d: d["non_pcaob_auditor_names"].str.split("; "))
    .explode("firm")
    .groupby("firm")
    .agg(advisers=("entity_key", "nunique"),
         total_aum=("assets_under_management", "sum"))
    .reset_index()
    .sort_values("advisers", ascending=False)
    .head(25)
)
st.dataframe(pd.DataFrame({
    "Auditor firm": firms["firm"],
    "Advisers":     firms["advisers"],
    "Total AUM":    firms["total_aum"].apply(fmt_aum),
}), use_container_width=True, hide_index=True)
