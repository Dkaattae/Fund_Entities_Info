import pandas as pd
import plotly.express as px
import streamlit as st

from bq import bq_client

st.set_page_config(page_title="Service Provider Directory", layout="wide")

st.title("Service Provider Directory")
st.caption(
    "Year-over-year adviser count per service provider, sourced from SEC ERA (Form ADV) annual filings. "
    "Each count is the number of distinct registered advisers that reported using the provider in that calendar year."
)

PROVIDER_TYPES = {
    "Auditors":      "AUDITOR",
    "Custodians":    "CUSTODIAN",
    "Fund Admins":   "FUND_ADMIN",
    "Prime Brokers": "PRIME_BROKER",
    "Marketers":     "MARKETER",
}


def fmt_pct(val) -> str:
    if pd.isna(val) or val is None:
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"


def pct_color(val) -> str:
    if pd.isna(val) or val is None:
        return "color: gray"
    return "color: #2ca02c" if val > 0 else ("color: #d62728" if val < 0 else "color: gray")


@st.cache_data(ttl=3600)
def load_yoy(provider_type: str) -> pd.DataFrame:
    client, project = bq_client()
    return client.query(f"""
        SELECT
            canonical_id,
            display_name,
            city,
            state,
            country,
            report_year,
            count_this_year,
            count_last_year,
            pct_change
        FROM `{project}.sec_filings_marts.service_provider_yoy`
        WHERE provider_type = '{provider_type}'
        ORDER BY count_this_year DESC, display_name
    """).to_dataframe()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    min_clients = st.number_input(
        "Min advisers (this year)",
        min_value=0,
        value=1,
        step=1,
        help="Hide providers with fewer than N advisers this year.",
    )
    top_n = st.slider("Top N for chart", min_value=5, max_value=50, value=20, step=5)

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

        # Apply min filter
        df = df[df["count_this_year"] >= min_clients].copy()

        if df.empty:
            st.info("No providers match the current filters.")
            continue

        # ── Summary metrics ───────────────────────────────────────────────
        total_this  = int(df["count_this_year"].sum())
        total_last  = int(df["count_last_year"].sum())
        grew        = int((df["pct_change"] > 0).sum())
        shrank      = int((df["pct_change"] < 0).sum())
        new_ones    = int((df["count_last_year"] == 0).sum())

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(f"Providers ({report_year})", len(df))
        c2.metric(f"Total adviser slots ({report_year})", f"{total_this:,}")
        c3.metric(f"vs {prior_year}", f"{total_last:,}")
        c4.metric("Grew YoY",   grew)
        c5.metric("New entrants", new_ones)

        st.divider()

        # ── Bar chart: top N by this-year count ───────────────────────────
        chart_df = df.head(top_n).copy()
        chart_df["display_name"] = chart_df["display_name"].fillna(chart_df["canonical_id"])

        fig = px.bar(
            chart_df.sort_values("count_this_year"),
            x="count_this_year",
            y="display_name",
            orientation="h",
            labels={
                "count_this_year": f"# Advisers ({report_year})",
                "display_name":    "",
            },
            title=f"Top {top_n} {label} by Adviser Count ({report_year})",
            height=max(350, top_n * 22),
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Detail table ──────────────────────────────────────────────────
        st.subheader(f"All {label}")

        display = pd.DataFrame({
            "Provider":              df["display_name"].fillna(df["canonical_id"]),
            f"# Advisers {report_year}": df["count_this_year"].astype(int),
            f"# Advisers {prior_year}":  df["count_last_year"].astype(int),
            "% Change":              df["pct_change"].apply(fmt_pct),
            "City":                  df["city"].fillna("—"),
            "State":                 df["state"].fillna("—"),
            "Country":               df["country"].fillna("—"),
        })

        # colour the % change column
        def _style_pct(col):
            return [
                ("color: #2ca02c" if "+" in v else ("color: #d62728" if v.startswith("-") else "color: gray"))
                if v != "—" else "color: gray"
                for v in col
            ]

        styled = display.style.apply(_style_pct, subset=["% Change"])

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
            with st.expander("Provider detail", expanded=True):
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Advisers {report_year}", int(row["count_this_year"]))
                c2.metric(f"Advisers {prior_year}",  int(row["count_last_year"]))
                c3.metric("% Change", fmt_pct(row.get("pct_change")))

                c4, c5, c6 = st.columns(3)
                c4.metric("City",    row.get("city") or "—")
                c5.metric("State",   row.get("state") or "—")
                c6.metric("Country", row.get("country") or "—")

                st.caption(f"Canonical ID: {row['canonical_id']}")
