"""Operator review interface for medium-confidence product matches."""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
import streamlit as st

from ui.api_client import api_get, api_post, get_api_url, is_connection_error
from ui.theme import (
    inject_theme,
    page_hero,
    confidence_pill,
    show_offline,
)

ADVANCE_DELAY_SECONDS = 1.5


def _init_session_state() -> None:
    """Ensure session counters and flags exist."""
    today = date.today().isoformat()
    if st.session_state.get("metrics_date") != today:
        st.session_state.metrics_date = today
        st.session_state.approved_today = 0
        st.session_state.rejected_today = 0

    defaults = {
        "current": None,
        "initial_pending": None,
        "reviewed_count": 0,
        "auto_advance": False,
        "last_toast": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _load_next() -> tuple[dict | None, bool]:
    """Fetch the next pending product. Returns (payload, api_offline)."""
    try:
        response = requests.get(f"{get_api_url()}/match/next", timeout=30)
        if response.status_code == 404:
            return None, False
        response.raise_for_status()
        return response.json(), False
    except requests.RequestException as exc:
        return None, is_connection_error(exc)


def _submit_decision(
    match_id: int,
    decision: str,
    note: str = "",
    *,
    count_session: bool = True,
) -> tuple[bool, bool]:
    """POST an operator decision. Returns (success, api_offline)."""
    ok, offline = api_post(
        f"/decision/{match_id}",
        json={"decision": decision, "note": note or None},
        timeout=30,
    )
    if ok and count_session:
        if decision == "approved":
            st.session_state.approved_today += 1
        else:
            st.session_state.rejected_today += 1
        st.session_state.reviewed_count += 1
    return ok, offline


def _operator_note() -> str:
    return st.session_state.get("operator_note", "")


def _handle_decision(match_id: int, decision: str, message: str) -> None:
    ok, offline = _submit_decision(match_id, decision, _operator_note())
    if offline:
        show_offline()
    if ok:
        st.session_state.last_toast = message
        st.session_state.auto_advance = True
        st.rerun()


def _advance_after_decision() -> None:
    """Show toast, wait, then load the next product."""
    if not st.session_state.auto_advance:
        return
    if st.session_state.last_toast:
        st.toast(st.session_state.last_toast, icon="✅")
    time.sleep(ADVANCE_DELAY_SECONDS)
    st.session_state.auto_advance = False
    st.session_state.last_toast = ""
    next_product, offline = _load_next()
    if offline:
        show_offline()
    st.session_state.current = next_product
    st.rerun()


st.set_page_config(page_title="Operator Review", page_icon="🔍", layout="wide", initial_sidebar_state="expanded")
inject_theme()
_init_session_state()

page_hero(
    "Operator Review",
    "Match unmatched Turkish products against the barcoded reference catalogue",
)

stats, stats_offline = api_get("/stats", timeout=5)
if stats_offline:
    show_offline()
if stats is None:
    st.error("Could not load statistics from the API.")
    st.stop()

if stats and st.session_state.initial_pending is None:
    st.session_state.initial_pending = stats.get("pending", 0)

pending_total = int(stats.get("pending", 0)) if stats else 0
match_rate = float(stats.get("match_rate", 0.0)) if stats else 0.0

with st.sidebar:
    st.markdown("#### Session metrics")
    st.metric("Total Pending", f"{pending_total:,}")
    st.metric("Approved Today", st.session_state.approved_today)
    st.metric("Rejected Today", st.session_state.rejected_today)
    st.metric("Match Rate", f"{match_rate:.1%}")

    if st.button("🔄 Refresh", use_container_width=True, key="sidebar_refresh"):
        next_product, offline = _load_next()
        if offline:
            show_offline()
        st.session_state.current = next_product
        st.rerun()

_advance_after_decision()

if st.session_state.current is None:
    next_product, offline = _load_next()
    if offline:
        show_offline()
    st.session_state.current = next_product

current = st.session_state.current

if current is None:
    total_matches = int(stats.get("auto_approved", 0)) + int(stats.get("rejected", 0)) + pending_total
    if total_matches == 0:
        st.warning(
            "No match records in the database yet. Go to the **app** home page and "
            "click **Run batch process** (~70 minutes for the full catalogue)."
        )
    else:
        st.balloons()
        st.success("All pending items reviewed!")
        st.caption("The review queue is empty.")
    st.stop()

left_col, right_col = st.columns(2, gap="large")

with left_col:
    brand = current.get("brand") or ""
    weight = current.get("weight") or ""
    tag_html = ""
    if brand:
        tag_html += f'<span class="tag tag-brand">🏷 {brand}</span>'
    if weight:
        tag_html += f'<span class="tag tag-weight">⚖ {weight}</span>'
    st.markdown(
        f'<div class="trendbox-panel">'
        f'<div class="trendbox-panel-title">Product to Match</div>'
        f'<p class="product-title">{current["product_name"]}</p>'
        f"{tag_html}"
        f'<p class="product-meta">Product ID · {current["product_id"]}</p>'
        f"</div>",
        unsafe_allow_html=True,
    )

with right_col:
    st.markdown('<div class="section-label">Top 3 Suggestions</div>', unsafe_allow_html=True)
    suggestions = current.get("suggestions", [])[:3]

    if not suggestions:
        st.info("No suggestions available for this product.")
    else:
        for suggestion in suggestions:
            label = suggestion.get("confidence_label", "MEDIUM")
            score = float(suggestion.get("confidence_score", 0))
            color = suggestion.get("confidence_color", "#64748b")

            with st.container(border=True):
                st.markdown(confidence_pill(label, score, color), unsafe_allow_html=True)
                st.markdown(
                    f'<p class="suggestion-name">{suggestion["name"]}</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<p class="suggestion-barcode">{suggestion["barcode"]}</p>',
                    unsafe_allow_html=True,
                )
                if suggestion.get("explanation"):
                    st.markdown(
                        f'<p class="suggestion-explanation">{suggestion["explanation"]}</p>',
                        unsafe_allow_html=True,
                    )

                if st.button(
                    "SELECT THIS MATCH",
                    key=f"select_{suggestion['match_id']}",
                    use_container_width=True,
                ):
                    _handle_decision(
                        suggestion["match_id"],
                        "approved",
                        f"Approved: {suggestion['name'][:40]}",
                    )

st.divider()

btn_col1, btn_col2 = st.columns(2)
top_match = next(
    (s for s in current.get("suggestions", []) if s.get("rank") == 1),
    current.get("suggestions", [{}])[0] if current.get("suggestions") else None,
)

with btn_col1:
    if st.button("✅ APPROVE TOP MATCH", type="primary", use_container_width=True, key="approve_top"):
        if top_match and top_match.get("match_id"):
            _handle_decision(top_match["match_id"], "approved", "Top match approved")
        else:
            st.error("No top match available.")

with btn_col2:
    if st.button("❌ REJECT ALL", use_container_width=True, key="reject_all"):
        pending_ids = [s["match_id"] for s in current.get("suggestions", []) if s.get("match_id")]
        if not pending_ids:
            st.error("Nothing to reject.")
        else:
            results = [
                _submit_decision(match_id, "rejected", _operator_note(), count_session=False)[0]
                for match_id in pending_ids
            ]
            if all(results):
                st.session_state.rejected_today += 1
                st.session_state.reviewed_count += 1
                st.session_state.last_toast = "All suggestions rejected"
                st.session_state.auto_advance = True
                st.rerun()
            elif any(results):
                st.warning("Some suggestions could not be rejected.")
            else:
                show_offline()

st.text_input(
    "Operator note (optional)",
    key="operator_note",
    placeholder="Add context for this decision…",
)

initial = st.session_state.initial_pending or 0
reviewed = st.session_state.reviewed_count
total = max(initial, reviewed + pending_total)
progress = min(reviewed / total, 1.0) if total else 0.0
st.progress(progress, text=f"{reviewed} of {total} products reviewed")
