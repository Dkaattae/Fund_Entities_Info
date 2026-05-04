import pandas as pd
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Service Provider Changes", layout="wide")

st.title("Service Provider Changes")
st.caption("SEC ERA (Form ADV) filings — current vs prior reporting year | SEC-registered advisers only")

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


def fmt_providers(arr) -> str:
    if not arr:
        return "—"
    return ", ".join(p.get("display_name", "") for p in arr if p)


def fmt_funds(arr) -> str:
    if not arr:
        return "—"
    return ", ".join(f.get("fund_name", "") for f in arr if f)


def primary_display_name(row) -> str:
    """Fund names if available, else adviser name."""
    funds = row.get("adviser_funds") or []
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
def load_new_advisers(current_year: int) -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            entity_key, legal_name, business_name,
            assets_under_management, date_submitted,
            is_initial_sec_era, is_initial_state_era
        FROM `{project}.sec_filings_marts.era_filing_history`
        WHERE is_initial_sec_era
          AND EXTRACT(YEAR FROM date_submitted) BETWEEN {current_year} AND {current_year} + 1
        ORDER BY date_submitted DESC
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
            reporting_year, prior_year,
            filing_date_current, filing_date_prior,
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

tab_labels = ["New Advisers", "Compliance Concerns"] + list(PROVIDER_TYPES.keys())
tabs = st.tabs(tab_labels)

# ── New Advisers ─────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader(f"New Advisers — {current_year} Initial ERA Filers")
    df = load_new_advisers(current_year)
    st.metric("Count", len(df))

    display = df[["legal_name", "business_name", "assets_under_management",
                   "date_submitted", "is_initial_sec_era"]].copy()
    display.columns = ["Legal Name", "Business Name", "AUM", "Filed", "Initial SEC ERA"]
    display["AUM"] = df["assets_under_management"].apply(fmt_aum)

    event = st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )
    rows = event.selection.rows
    if rows:
        row = df.iloc[rows[0]]
        with st.expander("Detail", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("Legal Name", row.get("legal_name") or "—")
            c2.metric("AUM", fmt_aum(row.get("assets_under_management")))
            c3.metric("Filed", str(row.get("date_submitted")))

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
        "Legal Name":       df["legal_name"].fillna(df["business_name"]),
        "AUM":              df["assets_under_management"].apply(fmt_aum),
        "FYE":              df["fiscal_year_end"],
        "Due Date":         df["due_date"].astype(str),
        "Days Overdue":     df["days_overdue"],
        "Last Filing":      df["last_filing_date"].astype(str),
        "City":             df["main_city"].fillna(""),
        "State":            df["main_state"].fillna(""),
    })
    st.dataframe(display, use_container_width=True, hide_index=True)

# ── Provider-type tabs ────────────────────────────────────────────────────────
for tab, (label, ptype) in zip(tabs[2:], PROVIDER_TYPES.items()):
    with tab:
        st.subheader(f"{label} Changes — {current_year} vs {prior_year}")
        df = load_provider_changes(ptype)

        if df.empty:
            st.info("No changes detected for this provider type.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total changes", len(df))
            c2.metric("New advisers",  int(df["is_new_adviser"].sum()))
            c3.metric("Added",         int((df["change_type"] == "added").sum()))
            c4.metric("Dropped",       int((df["change_type"] == "dropped").sum()))

            display = pd.DataFrame({
                "Fund(s)":         df.apply(primary_display_name, axis=1),
                "Adviser":         df["legal_name"].fillna(df["business_name"]),
                "AUM":             df["assets_under_management"].apply(fmt_aum),
                "FYE":             df["fiscal_year_end"],
                "Change":          df["change_type"].map(CHANGE_LABELS),
                f"{current_year}": df["providers_current"].apply(fmt_providers),
                f"{prior_year}":   df["providers_prior"].apply(fmt_providers),
                "Added":           df["providers_added"].apply(fmt_providers),
                "Dropped":         df["providers_dropped"].apply(fmt_providers),
                "Filed":           df["filing_date_current"].astype(str),
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
                adviser_name = row.get("legal_name") or row.get("business_name") or "—"
                st.subheader(adviser_name)
                if row.get("is_new_adviser"):
                    st.info(f"★ New adviser — first ERA filing in {current_year}, no prior data to compare.")

                # Show fund names with CIK
                funds = row.get("adviser_funds") or []
                if funds:
                    fund_df = pd.DataFrame(funds)[["fund_name", "fund_cik", "file_num"]].rename(
                        columns={"fund_name": "Fund", "fund_cik": "CIK", "file_num": "File No."})
                    st.dataframe(fund_df, use_container_width=True, hide_index=True)

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("AUM", fmt_aum(row.get("assets_under_management")))
                col2.metric("Fiscal Year End", row.get("fiscal_year_end") or "—")
                col3.metric(f"{current_year} Filing", str(row.get("filing_date_current")))
                col4.metric(f"{prior_year} Filing",
                            str(row.get("filing_date_prior")) if row.get("filing_date_prior") else "—")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**{current_year} Providers**")
                    providers_current = row.get("providers_current") or []
                    if providers_current:
                        st.dataframe(
                            pd.DataFrame(providers_current)[["display_name"]].rename(
                                columns={"display_name": "Name"}
                            ),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("None reported")

                with col_b:
                    st.markdown(f"**{prior_year} Providers**")
                    providers_prior = row.get("providers_prior") or []
                    if providers_prior:
                        st.dataframe(
                            pd.DataFrame(providers_prior)[["display_name"]].rename(
                                columns={"display_name": "Name"}
                            ),
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("None reported")

                added   = row.get("providers_added")   or []
                dropped = row.get("providers_dropped") or []

                if added:
                    st.success("**Added:** " + ", ".join(p.get("display_name", "") for p in added))
                if dropped:
                    st.error("**Dropped:** " + ", ".join(p.get("display_name", "") for p in dropped))
