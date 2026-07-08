import pandas as pd
import plotly.express as px
import streamlit as st

from bq import bq_client, run_query

st.set_page_config(page_title="Service Provider Directory", layout="wide")

st.title("Service Provider Directory")
st.caption(
    "Year-over-year adviser count per service provider, sourced from SEC ERA (Form ADV) annual filings. "
    "Each count is the number of distinct registered advisers that reported using the provider in that fiscal year."
)

PROVIDER_TYPES = {
    "Auditors":      "AUDITOR",
    "Custodians":    "CUSTODIAN",
    "Fund Admins":   "FUND_ADMIN",
    "Prime Brokers": "PRIME_BROKER",
    "Marketers":     "MARKETER",
}

# Registry ID columns to display per provider type, in order of preference.
# Empty list = no registry ID exists for this type (FUND_ADMIN).
REGISTRY_ID_COLS: dict[str, list[tuple[str, str]]] = {
    "AUDITOR":      [("pcaob_number", "PCAOB #")],
    "CUSTODIAN":    [("sec_number", "SEC #"), ("lei", "LEI")],
    "PRIME_BROKER": [("sec_number", "SEC #"), ("crd_number", "CRD #")],
    "MARKETER":     [("sec_number", "SEC #"), ("crd_number", "CRD #")],
    "FUND_ADMIN":   [],
}

SECTION_LABELS: dict[str, tuple[str, str]] = {
    "AUDITOR":      ("PCAOB Registered Auditors",               "No PCAOB Number"),
    "CUSTODIAN":    ("Registered Custodians (SEC # or LEI)",     "No Registry Number"),
    "PRIME_BROKER": ("Registered Prime Brokers (SEC # or CRD)", "No Registry Number"),
    "MARKETER":     ("Registered Marketers (SEC # or CRD)",     "No Registry Number"),
    "FUND_ADMIN":   ("", ""),
}

NO_ID_CAPTIONS: dict[str, str] = {
    "AUDITOR": (
        "Auditors reported without a PCAOB registration number. "
        "Many are non-US firms not required to register with PCAOB. "
        "Others may be domestic firms that have not yet registered or are filing incorrectly."
    ),
    "CUSTODIAN": (
        "Custodians reported without an SEC number or LEI. "
        "These are often non-US custodians or related-party custody arrangements."
    ),
    "PRIME_BROKER": (
        "Prime brokers reported without an SEC or CRD number. "
        "These are often non-US brokers or related-party arrangements."
    ),
    "MARKETER": (
        "Marketers reported without an SEC or CRD number. "
        "These are often placement agents or foreign distributors not registered with FINRA."
    ),
}


def fmt_pct(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"


def _fmt_id(col: str, val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    if col == "pcaob_number":
        return str(int(val))
    return str(val)


@st.cache_data(ttl=3600)
def load_yoy(provider_type: str) -> pd.DataFrame:
    _, project = bq_client()
    return run_query(f"""
        SELECT
            y.canonical_id,
            y.display_name,
            y.city,
            y.state,
            y.country,
            y.report_year,
            y.count_this_year,
            y.count_last_year,
            y.pct_change,
            d.pcaob_number,
            d.sec_number,
            d.crd_number,
            d.lei
        FROM `{project}.sec_filings_marts.service_provider_yoy` y
        LEFT JOIN `{project}.sec_filings_marts.service_provider_dim` d
            USING (canonical_id, provider_type)
        WHERE y.provider_type = '{provider_type}'
        ORDER BY y.count_this_year DESC, y.display_name
    """)


@st.cache_data(ttl=3600)
def load_non_pcaob_alert() -> pd.DataFrame:
    _, project = bq_client()
    return run_query(f"""
        WITH non_pcaob_clients AS (
            SELECT
                spc.display_name  AS auditor_name,
                spc.city          AS auditor_city,
                spc.country       AS auditor_country,
                c.entity_key      AS adviser_entity_key
            FROM `{project}.sec_filings_marts.service_provider_clients` spc,
            UNNEST(spc.clients) AS c
            WHERE spc.provider_type = 'AUDITOR'
              AND spc.pcaob_number IS NULL
              AND spc.display_name IS NOT NULL
        )
        SELECT
            nc.auditor_name,
            nc.auditor_city,
            nc.auditor_country,
            fr.adviser_legal_name,
            fr.primary_issuer_name       AS fund_name,
            fr.investment_fund_type      AS fund_type,
            fr.file_num,
            fr.first_raise_amount,
            fr.first_raise_date,
            fr.initial_filing_date
        FROM non_pcaob_clients nc
        JOIN `{project}.sec_filings_marts.form_d_first_raise` fr
            ON fr.adviser_entity_key = nc.adviser_entity_key
        ORDER BY fr.first_raise_amount DESC
    """)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    country_filter = st.radio(
        "Country",
        options=["All", "US only", "Non-US only"],
        index=0,
        help="US = country is 'United States' or blank; Non-US = all others.",
    )
    min_clients = st.number_input(
        "Min advisers (this year)",
        min_value=0,
        value=1,
        step=1,
        help="Hide providers with fewer than N advisers this year.",
    )
    top_n = st.slider("Top N for chart", min_value=5, max_value=50, value=20, step=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_display(
    rows: pd.DataFrame,
    report_year: int,
    prior_year: int,
    id_cols: list[tuple[str, str]],
) -> pd.DataFrame:
    d: dict = {
        "Provider":                  rows["display_name"].fillna(rows["canonical_id"]),
        f"# Advisers {report_year}": rows["count_this_year"].astype(int),
        f"# Advisers {prior_year}":  rows["count_last_year"].astype(int),
        "% Change":                  rows["pct_change"].apply(fmt_pct),
        "City":                      rows["city"].fillna("—"),
        "State":                     rows["state"].fillna("—"),
        "Country":                   rows["country"].fillna("—"),
    }
    for col, lbl in id_cols:
        d[lbl] = rows[col].apply(lambda v, c=col: _fmt_id(c, v))
    return pd.DataFrame(d)


def _render_table(
    display_df: pd.DataFrame,
    source_df: pd.DataFrame,
    report_year: int,
    prior_year: int,
    id_cols: list[tuple[str, str]],
    key: str,
) -> None:
    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
    )
    selected = event.selection.rows
    if selected:
        row = source_df.iloc[selected[0]]
        with st.expander("Provider detail", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Advisers {report_year}", int(row["count_this_year"]))
            c2.metric(f"Advisers {prior_year}",  int(row["count_last_year"]))
            c3.metric("% Change", fmt_pct(row.get("pct_change")))

            c4, c5, c6 = st.columns(3)
            c4.metric("City",    row.get("city") or "—")
            c5.metric("State",   row.get("state") or "—")
            c6.metric("Country", row.get("country") or "—")

            id_parts = [
                f"{lbl}: {_fmt_id(col, row.get(col))}"
                for col, lbl in id_cols
                if pd.notna(row.get(col))
            ]
            caption = "  ·  ".join(id_parts) + f"  ·  Canonical ID: {row['canonical_id']}"
            st.caption(caption)


# ---------------------------------------------------------------------------
# One tab per provider type
# ---------------------------------------------------------------------------
tabs = st.tabs(list(PROVIDER_TYPES.keys()))

for tab, (label, ptype) in zip(tabs, PROVIDER_TYPES.items()):
    with tab:
        df = load_yoy(ptype)

        if df.empty:
            st.info("No data available.")
            continue

        report_year = int(df["report_year"].iloc[0])
        prior_year  = report_year - 1

        # Apply country filter
        is_us = (
            df["country"].str.strip().str.lower().isin(["united states", "us", ""])
            | df["country"].isna()
        )
        if country_filter == "US only":
            df = df[is_us].copy()
        elif country_filter == "Non-US only":
            df = df[~is_us].copy()

        df = df[df["count_this_year"] >= min_clients].copy()

        if df.empty:
            st.info("No providers match the current filters.")
            continue

        # ── Summary metrics ───────────────────────────────────────────────
        total_this = int(df["count_this_year"].sum())
        total_last = int(df["count_last_year"].sum())
        grew       = int((df["pct_change"] > 0).sum())
        shrank     = int((df["pct_change"] < 0).sum())
        new_ones   = int((df["count_last_year"] == 0).sum())

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(f"Providers ({report_year})", len(df))
        c2.metric(f"Total adviser slots ({report_year})", f"{total_this:,}")
        c3.metric(f"vs {prior_year}", f"{total_last:,}")
        c4.metric("Grew YoY",    grew)
        c5.metric("New entrants", new_ones)

        st.divider()

        # ── Bar chart: top N ──────────────────────────────────────────────
        chart_df = df.head(top_n).copy()
        chart_df["display_name"] = chart_df["display_name"].fillna(chart_df["canonical_id"])
        fig = px.bar(
            chart_df.sort_values("count_this_year"),
            x="count_this_year",
            y="display_name",
            orientation="h",
            labels={"count_this_year": f"# Advisers ({report_year})", "display_name": ""},
            title=f"Top {top_n} {label} by Adviser Count ({report_year})",
            height=max(350, top_n * 22),
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Detail tables ─────────────────────────────────────────────────
        id_cols = REGISTRY_ID_COLS[ptype]

        if id_cols:
            # Split: has a registry ID (canonical_id is PCAOB:/SEC:/LEI:)
            # vs no registry ID (canonical_id is NAME:...)
            has_id = df[~df["canonical_id"].str.startswith("NAME:", na=False)].copy()
            no_id  = df[ df["canonical_id"].str.startswith("NAME:", na=False)].copy()

            label_has, label_no = SECTION_LABELS[ptype]

            st.subheader(f"{label_has} ({len(has_id)})")
            if has_id.empty:
                st.info(f"No registered {label.lower()} match the current filters.")
            else:
                _render_table(
                    _make_display(has_id, report_year, prior_year, id_cols),
                    has_id, report_year, prior_year, id_cols,
                    key=f"tbl_{ptype}_id",
                )

            st.divider()

            st.subheader(f"{label_no} ({len(no_id)})")
            if ptype in NO_ID_CAPTIONS:
                st.caption(NO_ID_CAPTIONS[ptype])
            if no_id.empty:
                st.info(f"No unregistered {label.lower()} match the current filters.")
            else:
                _render_table(
                    _make_display(no_id, report_year, prior_year, []),
                    no_id, report_year, prior_year, [],
                    key=f"tbl_{ptype}_noid",
                )

            # ── Alert: auditors only ──────────────────────────────────────
            if ptype == "AUDITOR":
                st.divider()
                with st.expander(
                    "Funds that raised money with a non-PCAOB auditor", expanded=False
                ):
                    st.caption(
                        "ERA-linked funds that had their first dollar raised but whose adviser "
                        "currently reports a non-PCAOB auditor. These funds may need to switch "
                        "to a PCAOB-registered auditor as they grow."
                    )
                    alert_df = load_non_pcaob_alert()
                    if alert_df.empty:
                        st.info("No matching funds found.")
                    else:
                        st.metric("Funds flagged", len(alert_df))
                        display_alert = pd.DataFrame({
                            "Fund":              alert_df["fund_name"],
                            "Fund Type":         alert_df["fund_type"].fillna("—"),
                            "Adviser":           alert_df["adviser_legal_name"].fillna("—"),
                            "Auditor":           alert_df["auditor_name"].fillna("—"),
                            "Auditor Country":   alert_df["auditor_country"].fillna("—"),
                            "Amount Raised ($)": alert_df["first_raise_amount"].apply(
                                lambda v: f"{int(v):,}" if pd.notna(v) else "—"
                            ),
                            "First Sale Date":   alert_df["first_raise_date"].astype(str),
                            "Initial Filing":    alert_df["initial_filing_date"].astype(str),
                        })
                        st.dataframe(display_alert, use_container_width=True, hide_index=True)

        else:
            # FUND_ADMIN: no registry IDs, single table
            st.subheader(f"All {label}")
            _render_table(
                _make_display(df, report_year, prior_year, []),
                df, report_year, prior_year, [],
                key=f"tbl_{ptype}",
            )
