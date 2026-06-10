"""Trendbox product matching — Streamlit home page."""

from __future__ import annotations

import requests
import streamlit as st

from ui.api_client import get_api_url

st.set_page_config(
    page_title="Trendbox Matching",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Trendbox Product Matching")
st.caption("Two-stage retrieve-then-rerank pipeline for Turkish product names")


def api_get(path: str) -> dict | None:
    """GET from the FastAPI backend; return JSON or None on failure."""
    try:
        response = requests.get(f"{get_api_url()}{path}", timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"API request failed: {exc}")
        return None


col1, col2, col3 = st.columns(3)

health = api_get("/health")
if health:
    col1.metric("Status", health["status"].upper())
    col2.metric("Products indexed", f"{health['products_indexed']:,}")
    col3.metric("Pending reviews", f"{health['pending_reviews']:,}")
else:
    st.warning(
        "Cannot reach the API. Start it with:\n\n"
        "`uvicorn api.main:app --reload --port 8000`"
    )

st.divider()

st.subheader("Quick actions")

action_col1, action_col2 = st.columns(2)

with action_col1:
    if st.button("Run batch process", type="primary", use_container_width=True):
        with st.spinner("Matching all unmatched products…"):
            try:
                response = requests.post(f"{get_api_url()}/batch_process", timeout=3600)
                response.raise_for_status()
                result = response.json()
                st.success(
                    f"Done — {result['total_suggestions']:,} suggestions: "
                    f"{result['auto_approved']:,} auto-approved, "
                    f"{result['auto_rejected']:,} auto-rejected, "
                    f"{result['pending']:,} pending review"
                )
            except requests.RequestException as exc:
                st.error(f"Batch process failed: {exc}")

with action_col2:
    stats = api_get("/stats")
    if stats:
        st.markdown(
            f"**Match rate:** {stats['match_rate']:.1%}  \n"
            f"**Avg confidence:** {stats['avg_confidence']:.3f}  \n"
            f"**Unmatched:** {stats['unmatched']:,} · **Matched:** {stats['matched']:,}"
        )

st.info("Use the sidebar pages **Review** and **Stats** to work the review queue.")
