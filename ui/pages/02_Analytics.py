"""Analytics dashboard — metrics, charts, and business impact."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import altair as alt
import pandas as pd
import streamlit as st

from ui.api_client import api_get
from ui.theme import inject_theme, page_hero, show_offline

CATALOG_TOTAL = 100_585
MANUAL_MINUTES_PER_PRODUCT = 2
REFRESH_SECONDS = 30


def _fetch_analytics() -> tuple[dict | None, bool]:
    """Load analytics payload from the API."""
    return api_get("/analytics", timeout=5)


def _delta(current: int | float, key: str) -> int | float | None:
    """Compute metric delta vs the previous refresh snapshot."""
    previous = st.session_state.analytics_prev.get(key)
    if previous is None:
        return None
    return current - previous


def _store_snapshot(data: dict) -> None:
    """Save current values for delta calculations on the next refresh."""
    stats = data["stats"]
    st.session_state.analytics_prev = {
        "matched": stats["matched"],
        "pending": stats["pending"],
        "auto_approved": stats["auto_approved"],
        "operator_approved": stats["operator_approved"],
        "auto_rejected": data["auto_rejected"],
    }


def _render_metrics(data: dict) -> None:
    stats = data["stats"]
    total = max(int(stats["total_products"]), int(data.get("catalog_total", CATALOG_TOTAL)))
    matched = int(stats["matched"])
    unmatched = int(stats["unmatched"])
    match_pct = (matched / unmatched * 100) if unmatched else 0.0

    st.markdown('<div class="section-label">Key Metrics</div>', unsafe_allow_html=True)
    row1 = st.columns(3)
    row2 = st.columns(3)

    row1[0].metric("Total Products", f"{total:,}")
    row1[1].metric(
        "Matched",
        f"{matched:,}",
        delta=_delta(matched, "matched"),
        help=f"{match_pct:.1f}% of unmatched products",
    )
    row1[1].caption(f"{match_pct:.1f}% of unmatched")
    row1[2].metric("Pending Review", f"{stats['pending']:,}", delta=_delta(stats["pending"], "pending"))

    row2[0].metric(
        "Auto-Approved",
        f"{stats['auto_approved']:,}",
        delta=_delta(stats["auto_approved"], "auto_approved"),
    )
    row2[1].metric(
        "Operator Approved",
        f"{stats['operator_approved']:,}",
        delta=_delta(stats["operator_approved"], "operator_approved"),
    )
    row2[2].metric(
        "Auto-Rejected",
        f"{data['auto_rejected']:,}",
        delta=_delta(data["auto_rejected"], "auto_rejected"),
    )


def _render_confidence_chart(data: dict) -> None:
    st.markdown('<div class="section-label">Confidence Distribution</div>', unsafe_allow_html=True)
    scores = data.get("confidence_scores") or []
    buckets = data.get("confidence_buckets") or {"high": 0, "medium": 0, "low": 0}

    if not scores:
        st.info("No match scores yet — run batch process to populate data.")
        return

    try:
        score_df = pd.DataFrame({"score": scores})
        score_df["bin"] = pd.cut(score_df["score"], bins=20, include_lowest=True)
        hist_df = score_df.groupby("bin", observed=True).size().reset_index(name="count")
        hist_df["bin_mid"] = hist_df["bin"].apply(lambda interval: float(interval.mid))
        hist_df["band"] = hist_df["bin_mid"].apply(
            lambda mid: "High" if mid >= 0.90 else ("Medium" if mid >= 0.60 else "Low")
        )

        chart = (
            alt.Chart(hist_df)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("bin_mid:Q", title="Confidence score", scale=alt.Scale(domain=[0, 1])),
                y=alt.Y("count:Q", title="Matches"),
                color=alt.Color(
                    "band:N",
                    title="Band",
                    scale=alt.Scale(
                        domain=["High", "Medium", "Low"],
                        range=["#2ECC71", "#F39C12", "#E74C3C"],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("bin_mid:Q", title="Score", format=".2f"),
                    alt.Tooltip("band:N", title="Band"),
                    alt.Tooltip("count:Q", title="Count"),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception as exc:
        st.warning(f"Could not render confidence chart: {exc}")

    ann1, ann2, ann3 = st.columns(3)
    ann1.markdown(f"🟢 **High (≥0.90):** {buckets['high']:,}")
    ann2.markdown(f"🟡 **Medium (0.60–0.90):** {buckets['medium']:,}")
    ann3.markdown(f"🔴 **Low (<0.60):** {buckets['low']:,}")


def _render_timeline(data: dict) -> None:
    st.markdown('<div class="section-label">Decision Timeline</div>', unsafe_allow_html=True)
    timeline = data.get("timeline") or []

    if not timeline:
        st.info("No approvals recorded yet.")
        return

    try:
        timeline_df = pd.DataFrame(timeline)
        timeline_df["time"] = pd.to_datetime(timeline_df["time"])

        chart = (
            alt.Chart(timeline_df)
            .mark_line(point={"filled": True, "size": 60}, color="#0ea5e9", strokeWidth=2.5)
            .encode(
                x=alt.X("time:T", title="Time"),
                y=alt.Y("cumulative:Q", title="Cumulative approvals"),
                tooltip=[
                    alt.Tooltip("time:T", title="Time"),
                    alt.Tooltip("cumulative:Q", title="Total approved"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception as exc:
        st.warning(f"Could not render timeline: {exc}")


def _render_recent_decisions(data: dict) -> None:
    st.markdown('<div class="section-label">Recent Decisions</div>', unsafe_allow_html=True)
    rows = data.get("recent_decisions") or []

    if not rows:
        st.info("No operator decisions yet.")
        return

    table_df = pd.DataFrame(rows)
    table_df.columns = ["Product Name", "Matched To", "Confidence", "Decision", "Time"]
    table_df["Confidence"] = table_df["Confidence"].map(lambda value: f"{float(value):.3f}")

    try:
        def _row_style(row: pd.Series) -> list[str]:
            if str(row["Decision"]).lower() == "approved":
                return ["background-color: #d1fae5; color: #065f46"] * len(row)
            return ["background-color: #fee2e2; color: #991b1b"] * len(row)

        st.dataframe(
            table_df.style.apply(_row_style, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    except Exception:
        st.dataframe(table_df, use_container_width=True, hide_index=True)


def _render_business_impact(data: dict) -> None:
    st.markdown('<div class="section-label">Business Impact</div>', unsafe_allow_html=True)
    auto_approved = int(data["stats"]["auto_approved"])
    minutes_saved = auto_approved * MANUAL_MINUTES_PER_PRODUCT
    hours_saved = minutes_saved / 60

    st.metric(
        "⏱️ Estimated Time Saved",
        f"{hours_saved:,.1f} hours",
        help=f"{auto_approved:,} auto-approved × {MANUAL_MINUTES_PER_PRODUCT} min per product",
    )
    st.markdown(
        f'<div class="impact-card"><p>💰 This system has saved your team '
        f"<strong>{hours_saved:,.1f} hours</strong> of manual work "
        f"({auto_approved:,} products × {MANUAL_MINUTES_PER_PRODUCT} min).</p></div>",
        unsafe_allow_html=True,
    )


def _render_dashboard() -> None:
    data, offline = _fetch_analytics()
    if offline:
        show_offline()
    if data is None:
        st.error("Could not load analytics data from the API.")
        return

    _render_metrics(data)
    st.divider()
    _render_confidence_chart(data)
    st.divider()
    _render_timeline(data)
    st.divider()
    _render_recent_decisions(data)
    st.divider()
    _render_business_impact(data)
    _store_snapshot(data)


st.set_page_config(page_title="Analytics", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
inject_theme()

page_hero(
    "Analytics Dashboard",
    f"Live pipeline metrics · refreshes every {REFRESH_SECONDS} seconds",
)

if "analytics_prev" not in st.session_state:
    st.session_state.analytics_prev = {}


@st.fragment(run_every=REFRESH_SECONDS)
def _auto_refresh_dashboard() -> None:
    _render_dashboard()


_auto_refresh_dashboard()
