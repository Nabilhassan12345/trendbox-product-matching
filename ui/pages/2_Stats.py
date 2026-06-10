"""Pipeline statistics dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from ui.api_client import api_get
from ui.theme import inject_theme, page_hero, show_offline

st.set_page_config(page_title="Stats", layout="wide", initial_sidebar_state="expanded")
inject_theme()

page_hero("Pipeline Statistics", "Aggregate matching and review counts from the API")

if st.button("Refresh", use_container_width=False):
    st.rerun()

stats, offline = api_get("/stats", timeout=5)
if offline:
    show_offline()
if stats is None:
    st.error("Could not load statistics from the API.")
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
