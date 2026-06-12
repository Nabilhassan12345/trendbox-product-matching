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
    </div>
    """,
    unsafe_allow_html=True,
)
