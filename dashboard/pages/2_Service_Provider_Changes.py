import pandas as pd
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Service Provider Changes", layout="wide")

st.title("Service Provider Changes")
st.caption("SEC ERA (Form ADV) filings — latest filing vs the one immediately before it | SEC-registered advisers only")

PROVIDER_TYPES = {
    "Auditors":      "AUDITOR",
    "Custodians":    "CUSTODIAN",
    "Fund Admins":   "FUND_ADMIN",
    "Prime Brokers": "PRIME_BROKER",
    "Marketers":     "MARKETER",
}

CHANGE_LABELS = {
    "new_adviser":   "★ New adviser",
    "no_prior_data": "⚠ No prior data",
    "swapped":       "↔ Swapped",
    "added":         "+ Added",
    "dropped":       "− Dropped",
    "unchanged":     "= Unchanged",
}


def _to_list(val) -> list:
    """Safely coerce a BQ ARRAY column value to a Python list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        return list(val)
    except TypeError:
        return []


def _struct_get(item, key: str, default="") -> str:
    """Get a key from a BQ STRUCT that may arrive as a dict or object."""
    if isinstance(item, dict):
        return item.get(key, default)
    try:
        return getattr(item, key, default)
    except Exception:
        return default


def fmt_providers(val) -> str:
    items = _to_list(val)
    if not items:
        return "—"
    return ", ".join(_struct_get(p, "display_name") for p in items if p is not None)


def fmt_funds(val) -> str:
    items = _to_list(val)
    if not items:
        return "—"
    return ", ".join(_struct_get(f, "fund_name") for f in items if f is not None)


def primary_display_name(row) -> str:
    funds = _to_list(row.get("adviser_funds"))
    if funds:
        return fmt_funds(funds)
    return row.get("legal_name") or row.get("business_name") or "—"


def fmt_aum(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    if val >= 1_000_000_000:
        return f"${val/1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    return f"${val:,.0f}"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_filter_options() -> tuple[list[str], list[str]]:
    """Return (sorted FYE months, available change_types) from the mart."""
    client, project = bq_client()
    df = client.query(f"""
        SELECT DISTINCT fiscal_year_end, change_type
        FROM `{project}.sec_filings_marts.service_provider_changes`
        WHERE change_type != 'unchanged'
    """).to_dataframe()
    fye_values = sorted(df["fiscal_year_end"].dropna().unique().tolist())
    change_values = sorted(df["change_type"].dropna().unique().tolist())
    return fye_values, change_values


@st.cache_data(ttl=3600)
def load_reporting_years() -> tuple[int, int]:
    client, project = bq_client()
    row = client.query(f"""
        SELECT
            MAX(annual_amendment_fiscal_year)     AS current_year,
            MAX(annual_amendment_fiscal_year) - 1 AS prior_year
        FROM `{project}.sec_filings_marts.era_filing_history`
        WHERE is_annual_amendment_era
          AND annual_amendment_fiscal_year IS NOT NULL
    """).to_dataframe().iloc[0]
    return int(row["current_year"]), int(row["prior_year"])


@st.cache_data(ttl=3600)
def load_transitions() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            entity_key,
            legal_name,
            business_name,
            assets_under_management,
            date_submitted,
            event_quarter_label,
            transition_type,
            iapd_url
        FROM `{project}.sec_filings_marts.era_adviser_transitions`
        ORDER BY date_submitted DESC NULLS LAST
    """).to_dataframe()


@st.cache_data(ttl=3600)
def load_compliance() -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            entity_key, legal_name, business_name,
            assets_under_management, fiscal_year_end,
            main_city, main_state,
            current_reporting_year, due_date, last_filing_date, days_overdue
        FROM `{project}.sec_filings_marts.adviser_filing_compliance`
        ORDER BY days_overdue DESC
    """).to_dataframe()


@st.cache_data(ttl=3600)
def load_provider_changes(provider_type: str) -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            entity_key, legal_name, business_name,
            assets_under_management, fiscal_year_end,
            filing_date_current, filing_date_prior,
            iapd_url,
            is_new_adviser, has_no_prior_filing, change_type,
            providers_current, providers_prior, providers_added, providers_dropped,
            adviser_funds
        FROM `{project}.sec_filings_marts.service_provider_changes`
        WHERE provider_type = '{provider_type}'
          AND change_type != 'unchanged'
        ORDER BY assets_under_management DESC NULLS LAST, legal_name
    """).to_dataframe()


# ---------------------------------------------------------------------------
# Tab layout
# ---------------------------------------------------------------------------

current_year, prior_year = load_reporting_years()
fye_options, change_options = load_filter_options()

# ---------------------------------------------------------------------------
# Sidebar filters (apply to provider-type tabs only)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    selected_changes = st.multiselect(
        "Change type",
        options=change_options,
        default=change_options,
        format_func=lambda x: CHANGE_LABELS.get(x, x),
    )

    selected_fye = st.multiselect(
        "Fiscal year end",
        options=fye_options,
        default=fye_options,
    )

tab_labels = ["New Advisers", "Compliance Concerns"] + list(PROVIDER_TYPES.keys())
tabs = st.tabs(tab_labels)

# ── New Advisers ──────────────────────────────────────────────────────────────
TRANSITION_LABELS = {
    "new_era":        "New SEC ERA",
    "era_to_ria":     "ERA → RIA (upgrade)",
    "new_ria":        "New RIA (no ERA history)",
    "era_withdrawal": "ERA Withdrawal",
    "new_state_era":  "New State ERA",
    "new_state_ria":  "New State RIA",
}

with tabs[0]:
    st.subheader("Adviser Transitions")
    df_t = load_transitions()
    df_t["label"] = df_t["transition_type"].map(TRANSITION_LABELS).fillna(df_t["transition_type"])

    # ── Summary counts ────────────────────────────────────────────────────────
    counts = df_t["transition_type"].value_counts()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("New SEC ERA",    int(counts.get("new_era",        0)))
    c2.metric("ERA → RIA",      int(counts.get("era_to_ria",     0)))
    c3.metric("ERA Withdrawn",  int(counts.get("era_withdrawal", 0)))
    c4.metric("New State ERA",  int(counts.get("new_state_era",  0)))
    c5.metric("New RIA",        int(counts.get("new_ria",        0)))
    c6.metric("New State RIA",  int(counts.get("new_state_ria",  0)))

    st.divider()

    # ── Transition matrix by quarter ──────────────────────────────────────────
    st.subheader("Transitions by Quarter")

    matrix = (
        df_t.groupby(["event_quarter_label", "label"])
        .size()
        .reset_index(name="count")
        .pivot(index="event_quarter_label", columns="label", values="count")
        .fillna(0)
        .astype(int)
        .reset_index()
        .rename(columns={"event_quarter_label": "Quarter"})
    )
    st.dataframe(matrix, use_container_width=True, hide_index=True)

    st.caption(
        "RIA → ERA downgrades are not shown — detecting them requires ingesting "
        "full Form ADV (registered adviser) data, which is a separate SEC bulk download."
    )

    st.divider()

    # ── Detail table with filter ───────────────────────────────────────────────
    st.subheader("Transition Events")

    label_options = sorted(df_t["label"].unique().tolist())
    selected_labels = st.multiselect(
        "Filter by transition type", label_options, default=label_options,
        key="transition_filter"
    )
    df_filtered = df_t[df_t["label"].isin(selected_labels)]

    display = pd.DataFrame({
        "Adviser":      df_filtered["business_name"].fillna(df_filtered["legal_name"]).fillna("— (RIA, name unavailable)"),
        "Transition":   df_filtered["label"],
        "AUM":          df_filtered["assets_under_management"].apply(fmt_aum),
        "Date":         df_filtered["date_submitted"].astype(str),
        "Quarter":      df_filtered["event_quarter_label"],
    })

    event = st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )
    rows = event.selection.rows
    if rows:
        row = df_filtered.iloc[rows[0]]
        with st.expander("Detail", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Adviser",    row.get("business_name") or row.get("legal_name") or "—")
            c2.metric("Transition", row.get("label") or "—")
            c3.metric("AUM",        fmt_aum(row.get("assets_under_management")))
            c4.metric("Date",       str(row.get("date_submitted")) if row.get("date_submitted") else "—")
            if row.get("iapd_url"):
                st.link_button("View on IAPD", row["iapd_url"])

# ── Compliance Concerns ───────────────────────────────────────────────────────
with tabs[1]:
    st.subheader(f"Compliance Concerns — {current_year} Filing Overdue")
    st.caption(
        "Advisers past their annual amendment due date (fiscal year end + 90 days) "
        f"with no {current_year} filing on record."
    )
    df = load_compliance()

    c1, c2, c3 = st.columns(3)
    c1.metric("Advisers overdue", len(df))
    c2.metric("Avg days overdue",
              f"{df['days_overdue'].mean():.0f}" if len(df) else "—")
    c3.metric("Total AUM overdue",
              fmt_aum(df["assets_under_management"].sum()) if len(df) else "—")

    display = pd.DataFrame({
        "Business Name": df["business_name"].fillna(df["legal_name"]),
        "AUM":           df["assets_under_management"].apply(fmt_aum),
        "FYE":           df["fiscal_year_end"],
        "Due Date":      df["due_date"].astype(str),
        "Days Overdue":  df["days_overdue"],
        "Last Filing":   df["last_filing_date"].astype(str),
        "City":          df["main_city"].fillna(""),
        "State":         df["main_state"].fillna(""),
    })
    st.dataframe(display, use_container_width=True, hide_index=True)

# ── Provider-type tabs ────────────────────────────────────────────────────────
for tab, (label, ptype) in zip(tabs[2:], PROVIDER_TYPES.items()):
    with tab:
        st.subheader(f"{label} Changes — Latest vs Prior Filing")
        df = load_provider_changes(ptype)

        # Apply sidebar filters
        if selected_changes:
            df = df[df["change_type"].isin(selected_changes)]
        if selected_fye:
            df = df[df["fiscal_year_end"].isin(selected_fye)]

        if df.empty:
            st.info("No results match the current filters.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total changes", len(df))
            c2.metric("New advisers",  int(df["is_new_adviser"].sum()))
            c3.metric("Added",         int((df["change_type"] == "added").sum()))
            c4.metric("Dropped",       int((df["change_type"] == "dropped").sum()))

            display = pd.DataFrame({
                "Fund(s)":           df.apply(primary_display_name, axis=1),
                "Adviser":           df["business_name"].fillna(df["legal_name"]),
                "AUM":               df["assets_under_management"].apply(fmt_aum),
                "FYE":               df["fiscal_year_end"],
                "Change":            df["change_type"].map(CHANGE_LABELS),
                "Current Providers": df["providers_current"].apply(fmt_providers),
                "Prior Providers":   df["providers_prior"].apply(fmt_providers),
                "Added":             df["providers_added"].apply(fmt_providers),
                "Dropped":           df["providers_dropped"].apply(fmt_providers),
                "Current Filing":    df["filing_date_current"].astype(str),
                "Prior Filing":      df["filing_date_prior"].astype(str),
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
                row = df.iloc[selected[0]]
                st.divider()
                adviser_name = row.get("business_name") or row.get("legal_name") or "—"
                st.subheader(adviser_name)
                if row.get("is_new_adviser"):
                    st.info("★ New adviser — first ERA filing, no prior data to compare.")

                funds = _to_list(row.get("adviser_funds"))
                if funds:
                    fund_rows = [
                        {
                            "Fund":     _struct_get(f, "fund_name"),
                            "CIK":      _struct_get(f, "fund_cik"),
                            "File No.": _struct_get(f, "file_num"),
                        }
                        for f in funds if f is not None
                    ]
                    st.dataframe(pd.DataFrame(fund_rows), use_container_width=True, hide_index=True)

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("AUM", fmt_aum(row.get("assets_under_management")))
                col2.metric("Fiscal Year End", row.get("fiscal_year_end") or "—")
                col3.metric("Current Filing", str(row.get("filing_date_current")))
                col4.metric("Prior Filing",
                            str(row.get("filing_date_prior")) if row.get("filing_date_prior") else "—")

                if row.get("iapd_url"):
                    st.link_button("View adviser on IAPD", row["iapd_url"])

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Current Providers**")
                    current = _to_list(row.get("providers_current"))
                    if current:
                        st.dataframe(
                            pd.DataFrame([{"Name": _struct_get(p, "display_name")} for p in current if p]),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("None reported")

                with col_b:
                    st.markdown("**Prior Providers**")
                    prior = _to_list(row.get("providers_prior"))
                    if prior:
                        st.dataframe(
                            pd.DataFrame([{"Name": _struct_get(p, "display_name")} for p in prior if p]),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("None reported")

                added   = _to_list(row.get("providers_added"))
                dropped = _to_list(row.get("providers_dropped"))
                if added:
                    st.success("**Added:** " + ", ".join(_struct_get(p, "display_name") for p in added if p))
                if dropped:
                    st.error("**Dropped:** " + ", ".join(_struct_get(p, "display_name") for p in dropped if p))
