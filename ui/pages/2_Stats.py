"""Pipeline statistics dashboard."""

from __future__ import annotations

import requests
import streamlit as st

from ui.api_client import get_api_url

st.set_page_config(page_title="Stats", layout="wide")
st.title("Pipeline statistics")

if st.button("Refresh"):
    st.rerun()

try:
    response = requests.get(f"{get_api_url()}/stats", timeout=30)
    response.raise_for_status()
    stats = response.json()
except requests.RequestException as exc:
    st.error(f"Failed to load stats: {exc}")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total products", f"{stats['total_products']:,}")
col2.metric("Barcoded", f"{stats['barcoded']:,}")
col3.metric("Unmatched", f"{stats['unmatched']:,}")
col4.metric("Match rate", f"{stats['match_rate']:.1%}")

st.divider()

col5, col6, col7, col8 = st.columns(4)
col5.metric("Pending review", f"{stats['pending']:,}")
col6.metric("Auto-approved", f"{stats['auto_approved']:,}")
col7.metric("Operator approved", f"{stats['operator_approved']:,}")
col8.metric("Rejected", f"{stats['rejected']:,}")

st.metric("Average confidence (rank 1)", f"{stats['avg_confidence']:.4f}")
