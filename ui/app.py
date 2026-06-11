"""Trendbox product matching — Streamlit home page."""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit runs this file as a script; add project root so `from ui.*` works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import streamlit as st

from ui.api_client import api_get, get_api_url, is_connection_error
from ui.theme import inject_theme, show_offline

st.set_page_config(
    page_title="Trendbox Matching",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

st.title("Trendbox Product Matching")
st.caption("Two-stage retrieve-then-rerank pipeline for Turkish product names")

health, health_offline = api_get("/health", timeout=5)
if health_offline:
    show_offline()

if health is None:
    st.error("Could not load health status from the API.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Status", health["status"].upper())
col2.metric("Products indexed", f"{health['products_indexed']:,}")
col3.metric("Pending reviews", f"{health['pending_reviews']:,}")

if health["pending_reviews"] == 0 and health["products_indexed"] > 0:
    st.warning(
        "No match records in the review queue. Run batch processing below "
        "(a few minutes for the full catalogue)."
    )

st.divider()

st.subheader("Quick actions")

action_col1, action_col2 = st.columns(2)

with action_col1:
    if st.button("Run batch process", type="primary", use_container_width=True):
        with st.spinner("Matching all unmatched products — this takes a few minutes…"):
            try:
                response = requests.post(f"{get_api_url()}/batch_process", timeout=7200)
                response.raise_for_status()
                result = response.json()
                st.success(
                    f"Done — {result['total_suggestions']:,} suggestions: "
                    f"{result['auto_approved']:,} auto-approved, "
                    f"{result['auto_rejected']:,} auto-rejected, "
                    f"{result['pending']:,} pending review"
                )
                st.rerun()
            except requests.RequestException as exc:
                if is_connection_error(exc):
                    show_offline()
                st.error(f"Batch process failed: {exc}")

with action_col2:
    stats, stats_offline = api_get("/stats", timeout=5)
    if stats_offline:
        show_offline()
    if stats:
        st.markdown(
            f"**Match rate:** {stats['match_rate']:.1%}  \n"
            f"**Avg confidence:** {stats['avg_confidence']:.3f}  \n"
            f"**Unmatched:** {stats['unmatched']:,} · **Matched:** {stats['matched']:,}"
        )

st.info("Use the sidebar pages **Review** and **Analytics** to work the review queue.")
