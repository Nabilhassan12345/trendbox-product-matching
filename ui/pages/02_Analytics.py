"""Analytics dashboard — Labelbox-style design with Plotly 2x2 chart grid."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from ui.api_client import api_get
from ui.utils.charts import base_layout, chart_pipeline_method_split
from ui.utils.tables import format_timestamp
from ui.utils.styles import (
    badge_html,
    inject_styles,
    render_page_header,
    render_page_nav,
    render_section_header,
    section_label,
    show_offline_card,
)
REFRESH_SECONDS = 30
PAGE_SIZE = 10
DEFAULT_MANUAL_MINUTES = 2

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Analytics · Trendbox",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles()

# Inject CSS for chart fade-in on initial load
st.markdown(
    """
    <style>
    /* Fade-in + slide-up for Plotly chart containers */
    [data-testid="stPlotlyChart"] {
        animation: chartFadeIn 0.5s ease forwards;
    }
    @keyframes chartFadeIn {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0);   }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Timeline filtering ────────────────────────────────────────────────────────

def _range_cutoff(range_key: str) -> datetime:
    """Return the inclusive start datetime for a date-range filter."""
    now = datetime.now(timezone.utc)
    if range_key == "Last 7 days":
        return now - timedelta(days=7)
    if range_key == "Last 30 days":
        return now - timedelta(days=30)
    if range_key == "Last 90 days":
        return now - timedelta(days=90)
    return datetime(now.year, 1, 1, tzinfo=timezone.utc)


def _filter_daily_outcomes(daily: list[dict], range_key: str) -> list[dict]:
    """Keep daily outcome rows inside the selected date window."""
    if not daily:
        return daily
    cutoff = _range_cutoff(range_key)
    filtered: list[dict] = []
    for row in daily:
        raw = row.get("day", "")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw)).replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                filtered.append(row)
        except Exception:
            filtered.append(row)
    return filtered


def _chart_confidence_buckets(buckets: dict[str, int]) -> go.Figure:
    """Horizontal bar chart for high / medium / low confidence bands."""
    labels = ["High (≥90%)", "Medium (60–90%)", "Low (<60%)"]
    values = [
        int(buckets.get("high", 0)),
        int(buckets.get("medium", 0)),
        int(buckets.get("low", 0)),
    ]
    colors = ["#10B981", "#F59E0B", "#EF4444"]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            marker_line_width=0,
            hovertemplate="%{y}: %{x:,}<extra></extra>",
        )
    )
    layout = base_layout(height=140)
    layout["xaxis"]["showgrid"] = True
    layout["yaxis"]["showgrid"] = False
    fig.update_layout(**layout)
    return fig


# ── Chart builders ────────────────────────────────────────────────────────────

def _chart_cumulative_line(daily: list[dict]) -> go.Figure:
    """Card 1: Cumulative approved matches — one point per real calendar day."""
    fig = go.Figure()
    if daily:
        df = pd.DataFrame(daily)
        df["day"] = pd.to_datetime(df["day"])
        df["cumulative"] = df["approved"].cumsum()
        fig.add_trace(
            go.Scatter(
                x=df["day"],
                y=df["cumulative"],
                mode="lines+markers",
                line=dict(color="#E8622A", width=2),
                marker=dict(size=6, color="#E8622A"),
                fill="tozeroy",
                fillcolor="rgba(232,98,42,0.08)",
                hovertemplate="%{x|%b %d, %Y}<br>%{y:,} matched<extra></extra>",
            )
        )
    layout = base_layout()
    layout["xaxis"]["tickformat"] = "%b %d"
    layout["xaxis"]["nticks"] = max(len(daily), 2)
    fig.update_layout(**layout)
    return fig


def _chart_daily_auto_approved_bar(daily: list[dict]) -> go.Figure:
    """Card 2: Auto-approved — one bar per day from real ``Match.created_at`` dates."""
    fig = go.Figure()
    if daily:
        labels = [pd.to_datetime(r["day"]).strftime("%b %d") for r in daily]
        values = [int(r.get("auto_approved", 0)) for r in daily]
        fig.add_trace(
            go.Bar(
                x=labels,
                y=values,
                marker_color="#E8622A",
                marker_line_width=0,
                hovertemplate="%{x}<br>Auto-approved: %{y:,}<extra></extra>",
            )
        )
    layout = base_layout()
    fig.update_layout(**layout)
    return fig


def _chart_daily_operator_bar(daily: list[dict]) -> go.Figure:
    """Card 3: Operator approved — one bar per day from real ``Decision.decided_at`` dates."""
    fig = go.Figure()
    if daily:
        labels = [pd.to_datetime(r["day"]).strftime("%b %d") for r in daily]
        values = [int(r.get("operator_approved", 0)) for r in daily]
        fig.add_trace(
            go.Bar(
                x=labels,
                y=values,
                marker_color="#E8622A",
                marker_line_width=0,
                hovertemplate="%{x}<br>Operator approved: %{y:,}<extra></extra>",
            )
        )
    layout = base_layout()
    fig.update_layout(**layout)
    return fig


def _chart_decisions_stacked(
    daily: list[dict],
    *,
    approved_total: int,
    rejected_total: int,
) -> go.Figure:
    """Card 4: Decisions — stacked bar with real daily approved/rejected counts."""
    fig = go.Figure()

    if daily:
        labels = [pd.to_datetime(r["day"]).strftime("%b %d") for r in daily]
        approved_vals = [int(r["approved"]) for r in daily]
        rejected_vals = [int(r["rejected"]) for r in daily]
        fig.add_trace(
            go.Bar(
                name="Approved",
                x=labels,
                y=approved_vals,
                marker_color="#E8622A",
                marker_line_width=0,
                hovertemplate="%{x}<br>Approved: %{y:,}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Bar(
                name="Rejected",
                x=labels,
                y=rejected_vals,
                marker_color="#3B82F6",
                marker_line_width=0,
                hovertemplate="%{x}<br>Rejected: %{y:,}<extra></extra>",
            )
        )
        fig.update_layout(barmode="stack")
    else:
        fig.add_trace(
            go.Bar(
                name="Approved",
                x=["Total"],
                y=[approved_total],
                marker_color="#E8622A",
                marker_line_width=0,
            )
        )
        fig.add_trace(
            go.Bar(
                name="Rejected",
                x=["Total"],
                y=[rejected_total],
                marker_color="#3B82F6",
                marker_line_width=0,
            )
        )
        fig.update_layout(barmode="group")

    layout = base_layout(show_legend=True)
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=1.02,
        xanchor="right",
        x=1.0,
        font=dict(size=10),
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(**layout)
    return fig


# ── Metric card renderer ──────────────────────────────────────────────────────

def _metric_card(label: str, value: int | str, fig: go.Figure, *, chart_key: str) -> None:
    """Render one cell of the 2x2 grid: label + big number + Plotly chart."""
    value_str = f"{value:,}" if isinstance(value, int) else str(value)
    st.markdown(
        f'<div class="lb-metric-label">{label} <span style="color:#D1D5DB;">ⓘ</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="lb-metric-value">{value_str}</div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False},
        key=chart_key,
    )


# ── Recent decisions table ────────────────────────────────────────────────────

def _filter_activity_rows(rows: list[dict], decision_filter: str) -> list[dict]:
    """Apply the decision/source filter to recent activity rows."""
    if decision_filter == "All":
        return rows
    if decision_filter == "Approved":
        return [r for r in rows if str(r.get("decision", "")).lower() == "approved"]
    if decision_filter == "Rejected":
        return [r for r in rows if str(r.get("decision", "")).lower() == "rejected"]
    if decision_filter == "Auto only":
        return [r for r in rows if str(r.get("source", "")).lower() == "auto"]
    if decision_filter == "Operator only":
        return [r for r in rows if str(r.get("source", "")).lower() == "operator"]
    return rows


def _render_decisions_table(rows: list[dict], decision_filter: str = "All") -> None:
    section_label("RECENT ACTIVITY")
    rows = _filter_activity_rows(rows, decision_filter)

    st.markdown(
        """
        <style>
        .decision-row { transition: background 0.1s ease; }
        .decision-row:hover { background: #F9FAFB !important; cursor: default; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not rows:
        st.markdown(
            '<div class="lb-card" style="color:#6B7280; text-align:center; padding:32px;">'
            "No activity matches this filter yet."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    if "decisions_page" not in st.session_state:
        st.session_state.decisions_page = 0

    total_rows = len(rows)
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(st.session_state.decisions_page, total_pages - 1)
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_rows)
    page_rows = rows[start_idx:end_idx]

    # Table header — grid has no border-strip column; rows carry border-left directly
    st.markdown(
        """
        <div style="border:1px solid #E5E7EB; border-radius:8px; overflow:hidden;">
        <div class="lb-table-header" style="display:grid;
             grid-template-columns:28px 1fr 1fr 110px 100px 130px;
             gap:8px; padding:8px 15px;">
          <span></span>
          <span>Product Name</span>
          <span>Matched To</span>
          <span>Confidence</span>
          <span>Decision</span>
          <span>Time</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for i, row in enumerate(page_rows):
        product    = row.get("product_name", "—")
        match_name = row.get("matched_to", "—")
        conf       = float(row.get("confidence", 0))
        decision   = str(row.get("decision", "—")).capitalize()
        ts = format_timestamp(str(row.get("time", "—")))

        is_approved = decision.lower() == "approved"
        # Colored left border applied directly on the row div — stretches full height
        left_border = "#10B981" if is_approved else "#EF4444"
        dec_color   = "#065F46" if is_approved else "#991B1B"
        bg          = "#FAFAFA" if i % 2 == 0 else "#FFFFFF"
        conf_label  = "HIGH" if conf >= 0.9 else ("MEDIUM" if conf >= 0.6 else "LOW")
        conf_badge  = badge_html(conf_label, conf)

        st.markdown(
            f"""
            <div class="decision-row" style="
                 display:grid;
                 grid-template-columns:28px 1fr 1fr 110px 100px 130px;
                 gap:8px; padding:10px 12px; border-top:1px solid #F3F4F6;
                 border-left:3px solid {left_border};
                 background:{bg}; font-size:13px; color:#374151; align-items:center;">
              <span style="color:#9CA3AF;">☐</span>
              <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"
                    title="{product}">{product[:40]}</span>
              <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;"
                    title="{match_name}">{match_name[:40]}</span>
              <span>{conf_badge}</span>
              <span style="font-weight:600; color:{dec_color};">{decision}</span>
              <span style="color:#9CA3AF;">{ts}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Total row — match header grid, no left border accent
    st.markdown(
        f"""
        <div class="lb-table-total" style="display:grid;
             grid-template-columns:28px 1fr 1fr 110px 100px 130px;
             gap:8px; padding:10px 15px; border-top:1px solid #E5E7EB;">
          <span></span>
          <span>Total ({total_rows:,})</span>
          <span></span><span></span><span></span><span></span>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Pagination
    pag_l, pag_r = st.columns([3, 2])
    with pag_r:
        prev_col, info_col, next_col = st.columns([1, 3, 1])
        with prev_col:
            if st.button("‹", key="pg_prev", disabled=page == 0):
                st.session_state.decisions_page -= 1
                st.rerun()
        with info_col:
            st.markdown(
                f'<div class="lb-pagination">'
                f"Rows per page: {PAGE_SIZE}&nbsp;&nbsp;"
                f"{start_idx + 1}–{end_idx} of {total_rows:,}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with next_col:
            if st.button("›", key="pg_next", disabled=page >= total_pages - 1):
                st.session_state.decisions_page += 1
                st.rerun()


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _render_dashboard() -> None:
    data, offline = api_get("/analytics", timeout=10)
    if offline:
        show_offline_card()
    if data is None:
        st.error("Could not load analytics data from the API.")
        return

    stats = data["stats"]
    date_range = st.session_state.get("date_range", "Last 30 days")
    daily_outcomes = _filter_daily_outcomes(
        data.get("daily_outcomes") or [],
        date_range,
    )
    recent_decisions = data.get("recent_decisions") or []
    confidence_buckets = data.get("confidence_buckets") or {"high": 0, "medium": 0, "low": 0}
    catalog_total = int(data.get("catalog_total") or stats.get("total_products", 0))
    auto_rejected = int(data.get("auto_rejected", 0))
    manual_minutes = int(data.get("manual_minutes_per_match", DEFAULT_MANUAL_MINUTES))
    pipeline_stats = data.get("pipeline_stats") or {}
    analytics_view = st.session_state.get("analytics_nav", "Throughput")

    matched = int(stats["matched"])
    auto_approved = int(stats["auto_approved"])
    operator_approved = int(stats["operator_approved"])
    rejected = int(stats.get("rejected", 0))
    pending = int(stats.get("pending", 0))
    unmatched_total = int(stats.get("unmatched", catalog_total))
    avg_confidence = float(stats.get("avg_confidence", 0.0))
    total_decisions = matched + rejected

    total_auto = auto_approved + auto_rejected
    hours_saved = (total_auto * manual_minutes) / 60
    processed = matched + rejected
    pct_done = processed / max(unmatched_total, 1)
    days_saved = int(hours_saved / 8)
    pct_display = pct_done * 100

    render_page_nav("analytics")

    _view_copy = {
        "Throughput": (
            "Throughput",
            "Volume trends, auto-approval rates, and recent match activity.",
        ),
        "Efficiency": (
            "Efficiency",
            "Time saved by automation and catalog completion progress.",
        ),
        "Quality": (
            "Quality",
            "Confidence score distribution across rank-1 suggestions.",
        ),
        "Pipeline": (
            "Pipeline",
            "How unmatched products were resolved — Stage 0 blocking vs ML matching.",
        ),
    }
    view_title, view_desc = _view_copy.get(analytics_view, _view_copy["Throughput"])

    render_page_header(
        view_title,
        view_desc,
        eyebrow="Trendbox · Analytics",
        meta="Refreshes every 30 seconds",
    )

    tab_col, range_col = st.columns([3, 1], gap="medium")
    with tab_col:
        st.radio(
            "View",
            ["Throughput", "Pipeline", "Efficiency", "Quality"],
            horizontal=True,
            label_visibility="collapsed",
            key="analytics_nav",
            index=0,
        )
    with range_col:
        if analytics_view == "Throughput":
            st.selectbox(
                "Date range",
                ["Last 30 days", "Last 7 days", "Last 90 days", "Year to date"],
                label_visibility="collapsed",
                key="date_range",
            )

    # ── THROUGHPUT ────────────────────────────────────────────────────────────
    if analytics_view == "Throughput":
        render_section_header(
            "Performance overview",
            "Charts use real event dates from the database — not estimated daily splits.",
        )

        if len(daily_outcomes) == 1:
            day_label = pd.to_datetime(daily_outcomes[0]["day"]).strftime("%B %d, %Y")
            st.caption(f"All activity in this window occurred on {day_label} (batch run).")
        elif not daily_outcomes:
            st.caption("No resolved matches in the selected date range.")

        filt_col, _ = st.columns([2, 4])
        with filt_col:
            decision_filter = st.selectbox(
                "Activity filter",
                ["All", "Approved", "Rejected", "Auto only", "Operator only"],
                key="decision_filter",
            )

        row1_c1, row1_c2 = st.columns(2, gap="medium")
        row2_c1, row2_c2 = st.columns(2, gap="medium")

        with row1_c1:
            with st.container(border=True):
                _metric_card(
                    "Matched",
                    matched,
                    _chart_cumulative_line(daily_outcomes),
                    chart_key="throughput_matched",
                )

        with row1_c2:
            with st.container(border=True):
                _metric_card(
                    "Auto-Approved",
                    auto_approved,
                    _chart_daily_auto_approved_bar(daily_outcomes),
                    chart_key="throughput_auto_approved",
                )

        with row2_c1:
            with st.container(border=True):
                _metric_card(
                    "Operator Approved",
                    operator_approved,
                    _chart_daily_operator_bar(daily_outcomes),
                    chart_key="throughput_operator_approved",
                )

        with row2_c2:
            with st.container(border=True):
                _metric_card(
                    "Decisions",
                    total_decisions,
                    _chart_decisions_stacked(
                        daily_outcomes,
                        approved_total=matched,
                        rejected_total=rejected,
                    ),
                    chart_key="throughput_decisions",
                )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            _render_decisions_table(recent_decisions, decision_filter)

    # ── PIPELINE ────────────────────────────────────────────────────────────
    elif analytics_view == "Pipeline":
        render_section_header(
            "Resolution breakdown",
            "Rank-1 outcomes from the live database — Stage 0 runs before TF-IDF and embeddings.",
        )
        p1, p2, p3, p4 = st.columns(4, gap="medium")
        with p1:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">STAGE 0 · EXACT</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(pipeline_stats.get("stage0_exact", 0)):,}</div>',
                    unsafe_allow_html=True,
                )
        with p2:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">STAGE 0 · FUZZY</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(pipeline_stats.get("stage0_fuzzy", 0)):,}</div>',
                    unsafe_allow_html=True,
                )
        with p3:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">ML RESOLVED</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(pipeline_stats.get("ml_resolved", 0)):,}</div>',
                    unsafe_allow_html=True,
                )
        with p4:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">STAGE 0 TOTAL</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(pipeline_stats.get("stage0_total", 0)):,}</div>',
                    unsafe_allow_html=True,
                )

        t1, t2, t3 = st.columns(3, gap="medium")
        with t1:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">AUTO-APPROVED</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(pipeline_stats.get("auto_approved", 0)):,}</div>',
                    unsafe_allow_html=True,
                )
        with t2:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">PENDING REVIEW</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value amber">{int(pipeline_stats.get("pending", 0)):,}</div>',
                    unsafe_allow_html=True,
                )
        with t3:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">AUTO-REJECTED</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(pipeline_stats.get("auto_rejected", 0)):,}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            section_label("RESOLUTION METHOD SPLIT (RANK-1)")
            st.plotly_chart(
                chart_pipeline_method_split(pipeline_stats),
                use_container_width=True,
                config={"displayModeBar": False},
                key="pipeline_method_split",
            )
            alias_rows = pipeline_stats.get("alias_index_rows")
            canonical = int(pipeline_stats.get("canonical_barcoded", 0))
            index_note = (
                f"Search index: {int(alias_rows):,} alias rows · "
                f"{canonical:,} canonical barcoded products in DB"
                if alias_rows is not None
                else f"Canonical barcoded products in DB: {canonical:,}"
            )
            st.caption(
                f"{int(pipeline_stats.get('unmatched_triaged', 0)):,} unmatched products triaged · "
                f"{index_note}"
            )

    # ── EFFICIENCY ──────────────────────────────────────────────────────────
    elif analytics_view == "Efficiency":
        render_section_header(
            "Automation impact",
            f"Estimated time saved (assumes {manual_minutes} min per manual match) "
            "and triage progress across unmatched products.",
        )
        e1, e2, e3, e4 = st.columns(4, gap="medium")
        with e1:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">PENDING REVIEW</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="lb-metric-value amber">{pending:,}</div>', unsafe_allow_html=True)
        with e2:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">AUTO-PROCESSED</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="lb-metric-value">{total_auto:,}</div>', unsafe_allow_html=True)
        with e3:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">HOURS SAVED</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(hours_saved):,}</div>',
                    unsafe_allow_html=True,
                )
        with e4:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">WORKING DAYS SAVED</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="lb-metric-value">{days_saved:,}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            left_col, right_col = st.columns([3, 2], gap="large")

            with left_col:
                section_label("ESTIMATED TIME SAVED")
                st.markdown(
                    f'<div id="impact-hours" style="font-size:36px; font-weight:700; '
                    f'color:#111827; margin-bottom:4px;">0 hours</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div style="font-size:13px; color:#6B7280;">'
                    f"Based on {manual_minutes} min per manual match (estimate) "
                    f"({total_auto:,} auto-processed products)"
                    "</div>",
                    unsafe_allow_html=True,
                )

            with right_col:
                st.markdown(
                    f'<div style="font-size:18px; font-weight:700; color:#111827; '
                    f'margin-bottom:8px;">{pct_done:.1%} complete</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    """
                    <div style="background:#F3F4F6; border-radius:4px; height:6px;
                                overflow:hidden; margin-bottom:6px;">
                      <div id="impact-bar-fill" style="
                           background:linear-gradient(90deg,#E8622A,#F97316);
                           height:100%; width:0%; border-radius:4px;
                           transition:width 1s cubic-bezier(.4,0,.2,1);"></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div style="font-size:12px; color:#9CA3AF; margin-top:4px;">'
                    f"= {days_saved:,} full working days saved"
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div style="font-size:12px; color:#6B7280; margin-top:6px;">'
                    f"{processed:,} of {unmatched_total:,} unmatched products triaged"
                    "</div>",
                    unsafe_allow_html=True,
                )

    # ── QUALITY ───────────────────────────────────────────────────────────────
    elif analytics_view == "Quality":
        render_section_header(
            "Match confidence",
            "How reliably the model ranks its top suggestion per product.",
        )
        q1, q2, q3 = st.columns(3, gap="medium")
        with q1:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">AVG CONFIDENCE</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{avg_confidence:.3f}</div>',
                    unsafe_allow_html=True,
                )
        with q2:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">HIGH CONFIDENCE</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value">{int(confidence_buckets.get("high", 0)):,}</div>',
                    unsafe_allow_html=True,
                )
        with q3:
            with st.container(border=True):
                st.markdown('<div class="lb-metric-label">NEEDS REVIEW</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="lb-metric-value amber">{int(confidence_buckets.get("medium", 0)):,}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            section_label("CONFIDENCE DISTRIBUTION (RANK-1 MATCHES)")
            st.plotly_chart(
                _chart_confidence_buckets(confidence_buckets),
                use_container_width=True,
                config={"displayModeBar": False},
                key="quality_confidence_distribution",
            )
            st.caption(
                f"Low confidence: {int(confidence_buckets.get('low', 0)):,} · "
                f"Medium: {int(confidence_buckets.get('medium', 0)):,} · "
                f"High: {int(confidence_buckets.get('high', 0)):,}"
            )

    # ── Last updated timestamp ─────────────────────────────────────────────────
    st.markdown(
        f'<div style="text-align:right; font-size:11px; color:#9CA3AF; '
        f'margin-top:8px;">Last updated: {datetime.now().strftime("%H:%M:%S")}</div>',
        unsafe_allow_html=True,
    )

    # ── Count-up animations + progress bar ────────────────────────────────────
    # Uses a retry loop (up to 3 s) so it works regardless of React render timing.
    # height=1 is safer than height=0 for cross-origin script execution.
    components.html(
        f"""
        <script>
        (function() {{
            var TARGET_HOURS  = {int(hours_saved)};
            var TARGET_BAR    = {pct_display:.1f};   /* percent 0-100 */

            function countUp(el, target, duration, suffix) {{
                if (target <= 0) {{
                    el.textContent = '0' + (suffix || '');
                    return;
                }}
                var start = 0;
                var step  = target / (duration / 16);
                var timer = setInterval(function() {{
                    start += step;
                    var val = Math.floor(start);
                    el.textContent = val.toLocaleString('en-US') + (suffix || '');
                    if (start >= target) {{
                        el.textContent = target.toLocaleString('en-US') + (suffix || '');
                        clearInterval(timer);
                    }}
                }}, 16);
            }}

            function runAnimations(doc) {{
                /* ── 4 metric-value big numbers ── */
                doc.querySelectorAll('.lb-metric-value').forEach(function(el) {{
                    /* skip if already animated (data-animated flag) */
                    if (el.dataset.animated) return;
                    el.dataset.animated = '1';
                    var raw = el.textContent.replace(/,/g, '').trim();
                    var num = parseInt(raw, 10);
                    if (!isNaN(num) && num > 0) {{
                        el.textContent = '0';
                        countUp(el, num, 1000, '');
                    }}
                }});

                /* ── Hours-saved count-up ── */
                var hoursEl = doc.getElementById('impact-hours');
                if (hoursEl && !hoursEl.dataset.animated) {{
                    hoursEl.dataset.animated = '1';
                    hoursEl.textContent = '0 hours';
                    countUp(hoursEl, TARGET_HOURS, 1200, ' hours');
                }}

                /* ── Progress bar fill ── */
                var bar = doc.getElementById('impact-bar-fill');
                if (bar && !bar.dataset.animated) {{
                    bar.dataset.animated = '1';
                    /* tiny delay so the CSS transition has a "from" state */
                    setTimeout(function() {{
                        bar.style.width = TARGET_BAR.toFixed(1) + '%';
                    }}, 80);
                }}
            }}

            /* Retry every 200 ms for up to 3 seconds (15 attempts) */
            var attempts = 0;
            function tryInit() {{
                var doc = window.parent.document;
                var metrics = doc.querySelectorAll('.lb-metric-value');
                var hoursEl = doc.getElementById('impact-hours');
                if ((metrics.length > 0 || hoursEl) ) {{
                    runAnimations(doc);
                }} else if (attempts < 15) {{
                    attempts++;
                    setTimeout(tryInit, 200);
                }}
            }}
            tryInit();
        }})();
        </script>
        """,
        height=1,
    )


# ── Session init ──────────────────────────────────────────────────────────────

if "analytics_prev" not in st.session_state:
    st.session_state.analytics_prev = {}


# ── Auto-refresh fragment ─────────────────────────────────────────────────────

@st.fragment(run_every=REFRESH_SECONDS)
def _auto_refresh() -> None:
    _render_dashboard()


_auto_refresh()
