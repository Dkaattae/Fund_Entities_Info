import pandas as pd
import streamlit as st

from bq import bq_client, run_query

st.set_page_config(page_title="Late Audit Reports", layout="wide")

st.title("Late Audit Reports")
st.caption(
    "Audited private funds whose adviser's latest Form ADV still reports the audit "
    "outstanding — opinion 'Report Not Yet Received' or statements not distributed to "
    "investors — past a custody-rule-style deadline (fiscal year end + 120 days; "
    "+ 180 for funds of funds). Advisers must promptly amend Schedule D 7.B.23 once "
    "audited statements go out, so an old unresolved answer means a missing report or "
    "a missing amendment. The deadline is a benchmark: ERAs are not literally subject "
    "to the custody rule's audit provision. Funds whose report came back with a "
    "qualified (non-clean) opinion are shown as their own category."
)

STATUS_LABELS = {
    "report_not_received": "Report not received",
    "not_distributed":     "Received, not distributed",
    "qualified_opinion":   "Qualified opinion",
    "clean":               "Clean",
}
PROBLEM_STATUSES = ["report_not_received", "not_distributed"]
STALE_FILING_MONTHS = 18


def fmt_money(x) -> str:
    if pd.isna(x):
        return "—"
    x = float(x)
    if x >= 1e9:
        return f"${x/1e9:,.1f}B"
    if x >= 1e6:
        return f"${x/1e6:,.0f}M"
    return f"${x:,.0f}"


@st.cache_data(ttl=3600)
def load_funds() -> pd.DataFrame:
    _, project = bq_client()
    df = run_query(f"""
        SELECT
            entity_key, legal_name, business_name, assets_under_management,
            fiscal_year_end, iapd_url, last_filing_date,
            fund_id, fund_name, fund_type, gross_asset_value, is_fund_of_funds,
            is_gaap, fs_distributed, audit_opinion, auditor_names,
            has_non_pcaob_auditor, audit_status, reporting_fye_date,
            distribution_deadline, is_overdue, days_overdue
        FROM `{project}.sec_filings_marts.fund_audit_compliance`
        ORDER BY days_overdue DESC NULLS LAST, gross_asset_value DESC NULLS LAST
    """)
    for col in ("gross_asset_value", "assets_under_management", "days_overdue"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["last_filing_date"] = pd.to_datetime(df["last_filing_date"])
    return df


df = load_funds()
df["is_stale_filer"] = df["last_filing_date"] < (
    pd.Timestamp.now() - pd.DateOffset(months=STALE_FILING_MONTHS)
)

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    selected_statuses = st.multiselect(
        "Audit status",
        options=list(STATUS_LABELS.keys()),
        default=PROBLEM_STATUSES,
        format_func=lambda s: STATUS_LABELS[s],
    )
    overdue_only = st.toggle(
        "Overdue only", value=True,
        help="Only funds past their distribution deadline. Turn off to see "
             "unresolved reports still inside the window.",
    )
    hide_stale = st.toggle(
        f"Hide stale filers (no filing in {STALE_FILING_MONTHS}+ months)",
        value=False,
        help="Advisers that also stopped filing — likely quiet wind-downs; "
             "they overlap the Missing ERA Filings page.",
    )
    fund_types = sorted(df["fund_type"].dropna().unique().tolist())
    selected_types = st.multiselect("Fund type", fund_types, default=[],
                                    help="Empty = all types.")
    min_days = st.number_input("Min days overdue", min_value=0, value=0, step=30)

filtered = df[df["audit_status"].isin(selected_statuses)] if selected_statuses else df.copy()
if overdue_only:
    filtered = filtered[filtered["is_overdue"]]
if hide_stale:
    filtered = filtered[~filtered["is_stale_filer"]]
if selected_types:
    filtered = filtered[filtered["fund_type"].isin(selected_types)]
if min_days:
    filtered = filtered[filtered["days_overdue"] >= min_days]

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
overdue = df[df["is_overdue"]]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overdue funds", f"{len(overdue):,}")
c2.metric("Advisers with overdue funds", f"{overdue['entity_key'].nunique():,}")
c3.metric("Overdue fund GAV", fmt_money(overdue["gross_asset_value"].sum()))
c4.metric("Median days overdue",
          f"{overdue['days_overdue'].median():.0f}" if len(overdue) else "—")

# ---------------------------------------------------------------------------
# Fund table
# ---------------------------------------------------------------------------
st.subheader(f"Funds ({len(filtered):,})")

display = pd.DataFrame({
    "Fund":          filtered["fund_name"].fillna(""),
    "Adviser":       filtered["business_name"].fillna(filtered["legal_name"]),
    "Status":        filtered["audit_status"].map(STATUS_LABELS),
    "Fund GAV":      filtered["gross_asset_value"].apply(fmt_money),
    "Type":          filtered["fund_type"].fillna(""),
    "FoF":           filtered["is_fund_of_funds"].map({True: "Y", False: ""}),
    "Deadline":      filtered["distribution_deadline"].astype(str),
    "Days Overdue":  filtered["days_overdue"],
    "Auditor(s)":    filtered["auditor_names"].fillna(""),
    "Last Filing":   filtered["last_filing_date"].dt.date.astype(str),
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
    st.subheader(row["fund_name"] or "—")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Adviser", row.get("business_name") or row.get("legal_name") or "—")
    c2.metric("Status", STATUS_LABELS.get(row["audit_status"], row["audit_status"]))
    c3.metric("Deadline", str(row.get("distribution_deadline")))
    c4.metric("Days overdue",
              int(row["days_overdue"]) if pd.notna(row["days_overdue"]) else "—")

    st.markdown(
        f"**Fund GAV:** {fmt_money(row.get('gross_asset_value'))} · "
        f"**Adviser AUM:** {fmt_money(row.get('assets_under_management'))} · "
        f"**FYE:** {row.get('fiscal_year_end') or '—'} "
        f"(reporting {row.get('reporting_fye_date')})  \n"
        f"**Opinion on filing:** {row.get('audit_opinion') or '—'} · "
        f"**Distributed:** {'Yes' if row.get('fs_distributed') else 'No'} · "
        f"**GAAP:** {'Yes' if row.get('is_gaap') else 'No'}  \n"
        f"**Auditor(s):** {row.get('auditor_names') or '—'}"
        + (" ⚠ includes non-PCAOB" if row.get("has_non_pcaob_auditor") else "")
        + f"  \n**Last filing:** {row['last_filing_date'].date()}"
        + (" — stale filer, also overdue on filings" if row.get("is_stale_filer") else "")
    )
    if pd.notna(row.get("iapd_url")) and row.get("iapd_url"):
        st.link_button("View adviser on IAPD", row["iapd_url"])

# ---------------------------------------------------------------------------
# Auditors with the most overdue reports
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Auditors with the most overdue reports")
st.caption(
    "By count of overdue funds naming them on the latest filing. A firm that is slow "
    "across many clients is a different signal than one late fund."
)

aud = (
    overdue.dropna(subset=["auditor_names"])
    .assign(auditor=lambda d: d["auditor_names"].str.split("; "))
    .explode("auditor")
    .groupby("auditor")
    .agg(overdue_funds=("fund_id", "count"),
         advisers=("entity_key", "nunique"),
         total_gav=("gross_asset_value", "sum"))
    .reset_index()
    .sort_values("overdue_funds", ascending=False)
    .head(25)
)
st.dataframe(pd.DataFrame({
    "Auditor":       aud["auditor"],
    "Overdue funds": aud["overdue_funds"],
    "Advisers":      aud["advisers"],
    "Fund GAV":      aud["total_gav"].apply(fmt_money),
}), use_container_width=True, hide_index=True)
