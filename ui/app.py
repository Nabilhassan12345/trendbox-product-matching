"""Trendbox product matching — Home page."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import streamlit as st
import streamlit.components.v1 as components

from ui.api_client import api_get, get_api_url, is_connection_error
from ui.utils.styles import (
    health_status_label,
    inject_styles,
    render_divider,
    render_page_header,
    render_page_nav,
    render_section_header,
)

REFRESH_SECONDS = 30

st.set_page_config(
    page_title="Trendbox · Home",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles()

# ── Data ──────────────────────────────────────────────────────────────────────

health, health_offline = api_get("/health", timeout=5)
stats, stats_offline = api_get("/stats", timeout=5)
quality_summary, _quality_offline = api_get("/quality/summary", timeout=5)

if health_offline or stats_offline:
    st.markdown(
        """
        <div class="offline-banner">
          <strong>⚠️ Cannot connect to backend</strong> —
          start with <code>python pipeline.py</code>
        </div>
        """,
        unsafe_allow_html=True,
    )

_h = health or {}
_s = stats or {}
products_indexed = int(_h.get("products_indexed", 0))
pending_reviews = int(_h.get("pending_reviews", 0))
status_text, dot_class, val_class = health_status_label(health)
match_rate = float(_s.get("match_rate", 0.0))
avg_confidence = float(_s.get("avg_confidence", 0.0))
unmatched = int(_s.get("unmatched", 0))
matched_count = int(_s.get("matched", 0))
total_products = int(_s.get("total_products", products_indexed))
_quality = quality_summary or {}
_integrity_pct = float(_quality.get("catalog_integrity_pct", 0.0)) * 100.0
_size_conflicts = int(_quality.get("size_conflict_count", 0))

# ── Layout ────────────────────────────────────────────────────────────────────

render_page_nav("home", alive=True)

render_page_header(
    "Product Matching",
    "Two-stage retrieve-then-rerank pipeline for Turkish retail product data.",
    eyebrow="Trendbox",
    live=True,
)

# ── System status ─────────────────────────────────────────────────────────────

render_section_header(
    "System status",
    "Live health of the matcher API and review queue depth.",
)

c1, c2, c3 = st.columns(3, gap="medium")

with c1:
    with st.container(border=True):
        st.markdown('<div class="lb-metric-label">API status</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="{val_class}">
              <span class="{dot_class}"></span>{status_text}
            </div>
            <p class="tb-section-desc" style="margin-top:4px;">
              Matcher and REST API
            </p>
            """,
            unsafe_allow_html=True,
        )

with c2:
    with st.container(border=True):
        st.markdown(
            '<div class="lb-metric-label">Products indexed</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div id="stat-indexed" class="lb-metric-value">0</div>', unsafe_allow_html=True)
        st.caption("Catalog rows in the search index")

with c3:
    pulse_cls = "alive-card-pending" if pending_reviews > 0 else ""
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="{pulse_cls}">
              <div class="lb-metric-label">Pending reviews</div>
              <div id="stat-pending" class="lb-metric-value amber">0</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Awaiting operator decision")

components.html(
    f"""
    <script>
    (function() {{
        var INDEXED = {products_indexed};
        var PENDING = {pending_reviews};
        function countUp(el, target, duration) {{
            if (target <= 0) {{ el.textContent = '0'; return; }}
            var start = 0, step = target / (duration / 16);
            var timer = setInterval(function() {{
                start += step;
                el.textContent = Math.floor(start).toLocaleString('en-US');
                if (start >= target) {{
                    el.textContent = target.toLocaleString('en-US');
                    clearInterval(timer);
                }}
            }}, 16);
        }}
        var n = 0;
        function tryInit() {{
            var doc = window.parent.document;
            var idx = doc.getElementById('stat-indexed');
            var pen = doc.getElementById('stat-pending');
            if (idx && pen) {{
                if (!idx.dataset.animated) {{ idx.dataset.animated = '1'; countUp(idx, INDEXED, 1000); }}
                if (!pen.dataset.animated) {{ pen.dataset.animated = '1'; countUp(pen, PENDING, 1000); }}
            }} else if (n++ < 15) setTimeout(tryInit, 200);
        }}
        tryInit();
    }})();
    </script>
    """,
    height=1,
)

render_divider()

# ── Primary actions ───────────────────────────────────────────────────────────

render_section_header(
    "Quick actions",
    "Run the batch matcher or open the analytics dashboard.",
)

act_l, act_r = st.columns(2, gap="medium")

with act_l:
    with st.container(border=True):
        st.markdown(
            """
            <div class="action-title">Run batch process</div>
            <div class="action-desc">
              Auto-approve high-confidence matches (&gt;90%) and queue
              the rest for operator review.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Run now", type="primary", use_container_width=True, key="btn_batch"):
            with st.spinner("Matching unmatched products — this may take a few minutes…"):
                try:
                    resp = requests.post(f"{get_api_url()}/batch_process", timeout=7200)
                    resp.raise_for_status()
                    result = resp.json()
                    st.session_state["last_batch_time"] = datetime.now().strftime("%H:%M · %b %d")
                    st.success(
                        f"Done — {result['total_suggestions']:,} suggestions: "
                        f"{result['auto_approved']:,} auto-approved, "
                        f"{result.get('auto_rejected', 0):,} rejected, "
                        f"{result['pending']:,} pending review."
                    )
                    st.rerun()
                except requests.RequestException as exc:
                    if is_connection_error(exc):
                        st.markdown(
                            '<div class="offline-banner">⚠️ Cannot connect to backend.</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.error(f"Batch process failed: {exc}")
        last_run = st.session_state.get("last_batch_time", "Never")
        st.markdown(f'<div class="action-meta">Last run: {last_run}</div>', unsafe_allow_html=True)

with act_r:
    with st.container(border=True):
        st.markdown(
            """
            <div class="action-title">View analytics</div>
            <div class="action-desc">
              Matching performance, operator decisions, and confidence
              distributions across the catalog.
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open dashboard", key="btn_dashboard", use_container_width=True):
            st.switch_page("pages/02_Analytics.py")
        st.markdown(
            '<div class="action-meta">Auto-refreshes every 30 seconds</div>',
            unsafe_allow_html=True,
        )

render_divider()


def _render_pipeline_snapshot() -> None:
    """Pipeline snapshot cards — polls /catalog/profile every fragment run."""
    catalog_profile, catalog_offline = api_get("/catalog/profile", timeout=10)
    quality_live, _ = api_get("/quality/summary", timeout=10)
    _profile = (catalog_profile or {}).get("profile") or {}
    _pipeline = (catalog_profile or {}).get("pipeline_stats") or {}
    _live = (catalog_profile or {}).get("live_stats") or {}
    _gaps = _profile.get("enrichment_gaps") or {}
    _alias_rows = _pipeline.get("alias_index_rows")
    _stage0 = int(_pipeline.get("stage0_total", 0))
    _missing_wt = float(_gaps.get("unmatched_missing_weight_pct", 0))
    _pending = int(_live.get("pending", 0))
    _integrity_live = float((quality_live or {}).get("catalog_integrity_pct", 0.0)) * 100.0
    _conflicts_live = int((quality_live or {}).get("size_conflict_count", 0))

    render_section_header(
        "Pipeline snapshot",
        "Catalog quality and resolution stats from the live database and profile report.",
    )

    p1, p2, p3, p4 = st.columns(4, gap="medium")
    with p1:
        with st.container(border=True):
            st.markdown('<div class="lb-metric-label">ALIAS INDEX ROWS</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="lb-metric-value">{int(_alias_rows):,}</div>'
                if _alias_rows is not None
                else '<div class="lb-metric-value">—</div>',
                unsafe_allow_html=True,
            )
    with p2:
        with st.container(border=True):
            st.markdown('<div class="lb-metric-label">STAGE 0 RESOLVED</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="lb-metric-value">{_stage0:,}</div>', unsafe_allow_html=True)
    with p3:
        with st.container(border=True):
            st.markdown('<div class="lb-metric-label">UNMATCHED MISSING WEIGHT</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="lb-metric-value">{_missing_wt:.1f}%</div>', unsafe_allow_html=True)
    with p4:
        with st.container(border=True):
            st.markdown('<div class="lb-metric-label">PENDING REVIEW</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="lb-metric-value amber">{_pending:,}</div>',
                unsafe_allow_html=True,
            )

    if catalog_offline or catalog_profile is None:
        st.caption("Pipeline profile unavailable — start the API and run `scripts/profile_data.py`.")
    else:
        btn_col, meta_col = st.columns([1, 3])
        with btn_col:
            if st.button("View pipeline details →", key="btn_pipeline", use_container_width=True):
                st.switch_page("pages/03_Pipeline.py")
        with meta_col:
            st.caption(
                f"Refreshes every {REFRESH_SECONDS} seconds · "
                f"Integrity {_integrity_live:.1f}% · "
                f"{_conflicts_live:,} size conflicts · "
                f"Last updated: {datetime.now().strftime('%H:%M:%S')}"
            )


@st.fragment(run_every=REFRESH_SECONDS)
def _pipeline_snapshot_auto_refresh() -> None:
    _render_pipeline_snapshot()


# ── Pipeline snapshot ─────────────────────────────────────────────────────────

_pipeline_snapshot_auto_refresh()

render_divider()

# ── Catalog snapshot ──────────────────────────────────────────────────────────

render_section_header("Catalog snapshot", "Aggregate matching statistics from the live database.")

st.markdown(
    f"""
    <div class="tb-kpi-footer">
      <div class="stat-item">Catalog <strong>{total_products:,}</strong></div>
      <div class="stat-sep"></div>
      <div class="stat-item">Match rate <strong>{match_rate:.1%}</strong></div>
      <div class="stat-sep"></div>
      <div class="stat-item">Avg confidence <strong>{avg_confidence:.3f}</strong></div>
      <div class="stat-sep"></div>
      <div class="stat-item">Unmatched <strong>{unmatched:,}</strong></div>
      <div class="stat-sep"></div>
      <div class="stat-item">Matched <strong>{matched_count:,}</strong></div>
      <div class="stat-sep"></div>
      <div class="stat-item">Integrity <strong>{_integrity_pct:.1f}%</strong></div>
      <div class="stat-sep"></div>
      <div class="stat-item">Size conflicts <strong>{_size_conflicts:,}</strong></div>
    </div>
    """,
    unsafe_allow_html=True,
)
