"""Pipeline and catalog quality — live profile data from API."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from ui.api_client import api_get
from ui.utils.styles import (
    inject_styles,
    progress_bar_html,
    render_page_header,
    render_page_nav,
    render_section_header,
    section_label,
    show_offline_card,
)

REFRESH_SECONDS = 30

st.set_page_config(
    page_title="Pipeline · Trendbox",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles()

st.markdown(
    """
    <style>
    [data-testid="stPlotlyChart"] {
        animation: chartFadeIn 0.5s ease forwards;
    }
    @keyframes chartFadeIn {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0);   }
    }
    .pipeline-metric-card {
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .pipeline-metric-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 14px rgba(0,0,0,0.06);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _base_layout(height: int = 180, show_legend: bool = False) -> dict:
    return dict(
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=0, r=0, t=8, b=0),
        showlegend=show_legend,
        transition=dict(duration=500, easing="cubic-in-out"),
        hoverlabel=dict(
            bgcolor="#111827",
            font_size=12,
            font_color="white",
            bordercolor="#111827",
        ),
        font=dict(
            family='-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            size=11,
            color="#6B7280",
        ),
        xaxis=dict(showgrid=False, showline=False, tickfont=dict(size=10)),
        yaxis=dict(showgrid=True, gridcolor="#F3F4F6", showline=False, tickfont=dict(size=10)),
    )


def _chart_pipeline_method_split(pipeline_stats: dict) -> go.Figure:
    labels = ["Stage 0 · Exact", "Stage 0 · Fuzzy", "ML"]
    values = [
        int(pipeline_stats.get("stage0_exact", 0)),
        int(pipeline_stats.get("stage0_fuzzy", 0)),
        int(pipeline_stats.get("ml_resolved", 0)),
    ]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=["#10B981", "#34D399", "#3B82F6"],
            marker_line_width=0,
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        )
    )
    layout = _base_layout(height=200)
    fig.update_layout(**layout)
    return fig


def _chart_triage_outcomes(pipeline_stats: dict) -> go.Figure:
    labels = ["Auto-approved", "Pending", "Auto-rejected"]
    values = [
        int(pipeline_stats.get("auto_approved", 0)),
        int(pipeline_stats.get("pending", 0)),
        int(pipeline_stats.get("auto_rejected", 0)),
    ]
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=["#E8622A", "#F59E0B", "#3B82F6"],
            marker_line_width=0,
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        )
    )
    layout = _base_layout(height=200)
    fig.update_layout(**layout)
    return fig


def _metric_value_html(
    elem_id: str,
    value: int,
    *,
    amber: bool = False,
) -> str:
    cls = "lb-metric-value amber" if amber else "lb-metric-value"
    return (
        f'<div id="{elem_id}" class="{cls}" data-pipeline-metric="1" '
        f'data-target="{value}">0</div>'
    )


def _inject_metric_countup() -> None:
    """Animate pipeline metric numbers (runs on each fragment refresh)."""
    components.html(
        """
        <script>
        (function() {
            function countUp(el, target, duration) {
                if (target <= 0) { el.textContent = '0'; return; }
                var start = 0, step = target / (duration / 16);
                var timer = setInterval(function() {
                    start += step;
                    el.textContent = Math.floor(start).toLocaleString('en-US');
                    if (start >= target) {
                        el.textContent = target.toLocaleString('en-US');
                        clearInterval(timer);
                    }
                }, 16);
            }
            function run() {
                var doc = window.parent.document;
                doc.querySelectorAll('[data-pipeline-metric]').forEach(function(el) {
                    var target = parseInt(el.getAttribute('data-target') || '0', 10);
                    countUp(el, target, 600);
                });
            }
            run();
            setTimeout(run, 200);
        })();
        </script>
        """,
        height=0,
    )


def _render_pipeline() -> None:
    """Render pipeline dashboard; polls /catalog/profile on each fragment run."""
    render_page_nav("pipeline", alive=True)

    refresh_col, _ = st.columns([1, 5])
    with refresh_col:
        if st.button("Refresh now", key="pipeline_refresh_now", use_container_width=True):
            st.rerun()

    data, offline = api_get("/catalog/profile", timeout=15)
    if offline:
        show_offline_card()
    if data is None:
        st.error(
            "Could not load catalog profile. Run "
            "`python scripts/profile_data.py` and ensure the API is running."
        )
        return

    profile = data.get("profile") or {}
    live_stats = data.get("live_stats") or {}
    pipeline_stats = data.get("pipeline_stats") or {}

    total_products = int(live_stats.get("total_products", 0))
    alias_rows = pipeline_stats.get("alias_index_rows")
    stage0_total = int(pipeline_stats.get("stage0_total", 0))
    pending = int(live_stats.get("pending", 0))
    auto_approved = int(pipeline_stats.get("auto_approved", 0))
    auto_rejected = int(pipeline_stats.get("auto_rejected", 0))
    ml_resolved = int(pipeline_stats.get("ml_resolved", 0))
    unmatched_triaged = int(pipeline_stats.get("unmatched_triaged", 0)) or 1
    reviewed_pct = (unmatched_triaged - pending) / unmatched_triaged

    render_page_header(
        "Data pipeline",
        "Catalog quality metrics and live matching index stats from the database.",
        eyebrow="Trendbox · Pipeline",
        live=True,
        meta=f"Refreshes every {REFRESH_SECONDS} seconds",
    )

    # ── Live snapshot ─────────────────────────────────────────────────────────

    render_section_header(
        "Live snapshot",
        "Current database and matcher index state — updates automatically.",
    )

    pending_pulse = "alive-card-pending" if pending > 0 else ""
    s1, s2, s3, s4 = st.columns(4, gap="medium")
    with s1:
        with st.container(border=True):
            st.markdown(
                '<div class="pipeline-metric-card">'
                '<div class="lb-metric-label">PRODUCTS IN DB</div>'
                f'{_metric_value_html("pipe-products", total_products)}'
                "</div>",
                unsafe_allow_html=True,
            )
    with s2:
        with st.container(border=True):
            if alias_rows is not None:
                alias_metric = _metric_value_html("pipe-alias", int(alias_rows))
            else:
                alias_metric = '<div class="lb-metric-value">—</div>'
            st.markdown(
                '<div class="pipeline-metric-card">'
                '<div class="lb-metric-label">ALIAS INDEX ROWS</div>'
                f"{alias_metric}"
                "</div>",
                unsafe_allow_html=True,
            )
    with s3:
        with st.container(border=True):
            st.markdown(
                '<div class="pipeline-metric-card">'
                '<div class="lb-metric-label">STAGE 0 RESOLVED</div>'
                f'{_metric_value_html("pipe-stage0", stage0_total)}'
                "</div>",
                unsafe_allow_html=True,
            )
    with s4:
        with st.container(border=True):
            st.markdown(
                f'<div class="pipeline-metric-card {pending_pulse}">'
                '<div class="lb-metric-label">PENDING REVIEW</div>'
                f'{_metric_value_html("pipe-pending", pending, amber=True)}'
                "</div>",
                unsafe_allow_html=True,
            )

    _inject_metric_countup()

    # ── Live charts + review progress ─────────────────────────────────────────

    render_section_header(
        "Resolution & triage",
        "Live breakdown from rank-1 match outcomes in the database.",
    )

    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex; justify-content:space-between; '
            f'align-items:center; margin-bottom:10px;">'
            f'<div class="section-label" style="margin:0;">REVIEW PROGRESS</div>'
            f'<div style="font-size:22px; font-weight:700; color:#111827;">'
            f"{reviewed_pct:.1%}</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:13px; color:#6B7280; margin-bottom:8px;">'
            f"{unmatched_triaged - pending:,} of {unmatched_triaged:,} products no longer pending"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            progress_bar_html(reviewed_pct, color="#E8622A", bar_id="pipe-review-bar"),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    chart_l, chart_r = st.columns(2, gap="medium")
    with chart_l:
        with st.container(border=True):
            section_label("RESOLUTION METHOD (RANK-1)")
            st.plotly_chart(
                _chart_pipeline_method_split(pipeline_stats),
                use_container_width=True,
                config={"displayModeBar": False},
                key="pipeline_method_chart",
            )
    with chart_r:
        with st.container(border=True):
            section_label("TRIAGE OUTCOMES (RANK-1)")
            st.plotly_chart(
                _chart_triage_outcomes(pipeline_stats),
                use_container_width=True,
                config={"displayModeBar": False},
                key="pipeline_triage_chart",
            )

    # ── Batch triage cards ────────────────────────────────────────────────────

    render_section_header(
        "Last batch triage",
        "Rank-1 product outcomes from the live match table.",
    )

    t1, t2, t3, t4 = st.columns(4, gap="medium")
    with t1:
        with st.container(border=True):
            st.markdown(
                '<div class="pipeline-metric-card">'
                '<div class="lb-metric-label">AUTO-APPROVED</div>'
                f'{_metric_value_html("pipe-approved", auto_approved)}'
                "</div>",
                unsafe_allow_html=True,
            )
    with t2:
        with st.container(border=True):
            st.markdown(
                f'<div class="pipeline-metric-card {pending_pulse}">'
                '<div class="lb-metric-label">PENDING</div>'
                f'{_metric_value_html("pipe-triage-pending", pending, amber=True)}'
                "</div>",
                unsafe_allow_html=True,
            )
    with t3:
        with st.container(border=True):
            st.markdown(
                '<div class="pipeline-metric-card">'
                '<div class="lb-metric-label">AUTO-REJECTED</div>'
                f'{_metric_value_html("pipe-rejected", auto_rejected)}'
                "</div>",
                unsafe_allow_html=True,
            )
    with t4:
        with st.container(border=True):
            st.markdown(
                '<div class="pipeline-metric-card">'
                '<div class="lb-metric-label">ML RESOLVED</div>'
                f'{_metric_value_html("pipe-ml", ml_resolved)}'
                "</div>",
                unsafe_allow_html=True,
            )

    _inject_metric_countup()

    # ── Catalog profile (CSV snapshot) ──────────────────────────────────────

    render_section_header(
        "Catalog profile",
        "Static CSV snapshot from `data/reports/catalog_profile.json` "
        "(regenerate with `scripts/profile_data.py` when the CSV changes).",
    )

    row_counts = profile.get("row_counts") or {}
    dupes = profile.get("barcode_duplicates") or {}
    collisions = profile.get("name_collisions") or {}
    gaps = profile.get("enrichment_gaps") or {}
    dedupe = profile.get("dedupe_impact") or {}

    c1, c2 = st.columns(2, gap="medium")

    with c1:
        with st.container(border=True):
            section_label("RAW CSV ROWS")
            st.markdown(
                f"""
                | Metric | Count |
                |--------|------:|
                | Total rows | {int(row_counts.get('total', 0)):,} |
                | Barcoded | {int(row_counts.get('barcoded', 0)):,} |
                | Unmatched | {int(row_counts.get('unmatched', 0)):,} |
                """,
            )

    with c2:
        with st.container(border=True):
            section_label("BARCODE DUPLICATES")
            st.markdown(
                f"""
                | Metric | Count |
                |--------|------:|
                | Duplicate barcode rows | {int(dupes.get('duplicate_barcode_rows', 0)):,} |
                | Barcodes with multiple rows | {int(dupes.get('barcodes_with_multiple_rows', 0)):,} |
                | Barcodes with multiple spellings | {int(dupes.get('barcodes_with_multiple_spellings', 0)):,} |
                """,
            )

    c3, c4 = st.columns(2, gap="medium")

    with c3:
        with st.container(border=True):
            section_label("NAME COLLISIONS")
            st.markdown(
                f"""
                | Metric | Count |
                |--------|------:|
                | Names → multiple barcodes | {int(collisions.get('name_clean_mapping_to_multiple_barcodes', 0)):,} |
                | Unmatched/barcoded name overlap | {int(collisions.get('unmatched_barcoded_exact_name_clean_overlap', 0)):,} |
                """,
            )

    with c4:
        with st.container(border=True):
            section_label("ENRICHMENT GAPS")
            st.markdown(
                f"""
                | Metric | Value |
                |--------|------:|
                | Unmatched missing weight | {gaps.get('unmatched_missing_weight_pct', 0):.1f}% |
                | Barcoded missing weight | {gaps.get('barcoded_missing_weight_pct', 0):.1f}% |
                | Short unmatched names (&lt;8 chars) | {int(gaps.get('unmatched_short_names_lt_8_chars', 0)):,} |
                """,
                unsafe_allow_html=True,
            )

    render_section_header(
        "Dedupe impact",
        "How canonical database load differs from the raw CSV (first row kept per barcode).",
    )

    with st.container(border=True):
        st.markdown(
            f"""
            | Stage | Before | After | Dropped |
            |-------|-------:|------:|--------:|
            | Barcoded rows | {int(dedupe.get('barcoded_rows_before', 0)):,} | {int(dedupe.get('barcoded_rows_after', 0)):,} | {int(dedupe.get('barcoded_rows_dropped', 0)):,} |
            | Unmatched rows | {int(dedupe.get('unmatched_rows_before', 0)):,} | {int(dedupe.get('unmatched_rows_after', 0)):,} | {int(dedupe.get('unmatched_rows_dropped', 0)):,} |
            | **Total in DB** | — | **{int(dedupe.get('total_rows_after_dedupe', 0)):,}** | — |
            """,
        )

    st.caption(
        "Full architecture: see `docs/DATA_PIPELINE.md` in the repository. "
        "Live sections read from SQLite; catalog profile tables read from the JSON snapshot."
    )
    st.markdown(
        f'<div class="tb-page-meta" style="text-align:right; margin-top:8px;">'
        f'<span class="live-dot"></span>Last updated: {datetime.now().strftime("%H:%M:%S")}'
        f"</div>",
        unsafe_allow_html=True,
    )


@st.fragment(run_every=REFRESH_SECONDS)
def _auto_refresh() -> None:
    _render_pipeline()


_auto_refresh()
