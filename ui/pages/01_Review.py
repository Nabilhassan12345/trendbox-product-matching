"""Operator review interface for medium-confidence product matches."""

from __future__ import annotations

import time
from datetime import date

import requests
import streamlit as st

from ui.api_client import get_api_url

CONFIDENCE_BADGE = {
    "HIGH": "🟢 HIGH",
    "MEDIUM": "🟡 MEDIUM",
    "LOW": "🔴 LOW",
}

OFFLINE_MESSAGE = (
    "⚠️ Cannot connect to backend. Make sure pipeline.py is running."
)


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
        "api_online": True,
        "auto_advance": False,
        "last_toast": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _api_get(path: str) -> dict | None:
    """GET from API; return None and mark offline on connection failure."""
    try:
        response = requests.get(f"{get_api_url()}{path}", timeout=30)
        response.raise_for_status()
        st.session_state.api_online = True
        return response.json()
    except requests.ConnectionError:
        st.session_state.api_online = False
        return None
    except requests.RequestException:
        st.session_state.api_online = True
        return None


def _load_next() -> dict | None:
    """Fetch the next pending product from the review queue."""
    try:
        response = requests.get(f"{get_api_url()}/match/next", timeout=30)
        st.session_state.api_online = True
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except requests.ConnectionError:
        st.session_state.api_online = False
        return None
    except requests.RequestException:
        return None


def _submit_decision(
    match_id: int,
    decision: str,
    note: str = "",
    *,
    count_session: bool = True,
) -> bool:
    """POST an operator decision; optionally update session counters on success."""
    try:
        response = requests.post(
            f"{get_api_url()}/decision/{match_id}",
            json={"decision": decision, "note": note or None},
            timeout=30,
        )
        response.raise_for_status()
        st.session_state.api_online = True
        if count_session:
            if decision == "approved":
                st.session_state.approved_today += 1
            else:
                st.session_state.rejected_today += 1
            st.session_state.reviewed_count += 1
        return True
    except requests.ConnectionError:
        st.session_state.api_online = False
        return False
    except requests.RequestException:
        return False


def _confidence_badge(label: str) -> str:
    return CONFIDENCE_BADGE.get(label.upper(), f"⚪ {label}")


def _render_tags(brand: str | None, weight: str | None) -> None:
    tags = []
    if brand:
        tags.append(f"<span style='background:#E8F4FD;color:#1A5276;padding:4px 10px;"
                      f"border-radius:12px;font-size:0.85rem;margin-right:6px;'>🏷 {brand}</span>")
    if weight:
        tags.append(f"<span style='background:#FEF9E7;color:#7D6608;padding:4px 10px;"
                      f"border-radius:12px;font-size:0.85rem;'>⚖ {weight}</span>")
    if tags:
        st.markdown("".join(tags), unsafe_allow_html=True)


def _operator_note() -> str:
    return st.session_state.get("operator_note", "")


def _handle_decision(match_id: int, decision: str, message: str) -> None:
    if _submit_decision(match_id, decision, _operator_note()):
        st.session_state.last_toast = message
        st.session_state.auto_advance = True
        st.rerun()


st.set_page_config(page_title="Operator Review", layout="wide", initial_sidebar_state="expanded")
_init_session_state()

st.markdown(
    """
    <style>
    div[data-testid="column"]:nth-of-type(2) button[kind="secondary"] {
        background-color: #E74C3C;
        color: white;
        border: none;
    }
    div[data-testid="column"]:nth-of-type(2) button[kind="secondary"]:hover {
        background-color: #C0392B;
        color: white;
        border: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("# 🔍 Trendbox Product Matching — Operator Review")

stats = _api_get("/stats")
if stats and st.session_state.initial_pending is None:
    st.session_state.initial_pending = stats.get("pending", 0)

if not st.session_state.api_online:
    st.warning(OFFLINE_MESSAGE)
    st.stop()

with st.sidebar:
    st.subheader("Session metrics")
    pending_total = stats["pending"] if stats else 0
    match_rate = stats["match_rate"] if stats else 0.0

    st.metric("Total Pending", f"{pending_total:,}")
    st.metric("Approved Today", st.session_state.approved_today)
    st.metric("Rejected Today", st.session_state.rejected_today)
    st.metric("Match Rate %", f"{match_rate:.1%}")

    if st.button("🔄 Refresh", use_container_width=True):
        st.session_state.current = _load_next()
        fresh_stats = _api_get("/stats")
        if fresh_stats:
            stats = fresh_stats
        st.rerun()

if st.session_state.auto_advance:
    if st.session_state.last_toast:
        st.toast(st.session_state.last_toast, icon="✅")
    time.sleep(1.5)
    st.session_state.auto_advance = False
    st.session_state.last_toast = ""
    st.session_state.current = _load_next()
    st.rerun()

if st.session_state.current is None:
    st.session_state.current = _load_next()

if not st.session_state.api_online:
    st.warning(OFFLINE_MESSAGE)
    st.stop()

current = st.session_state.current

if current is None:
    st.balloons()
    st.success("✅ All products reviewed!")
    st.stop()

left_col, right_col = st.columns(2, gap="large")

with left_col:
    st.markdown("### Product to Match")
    st.markdown(f"## {current['product_name']}")
    _render_tags(current.get("brand"), current.get("weight"))
    st.markdown(
        f"<p style='color:#888;font-size:0.85rem;margin-top:12px;'>"
        f"Product ID: {current['product_id']}</p>",
        unsafe_allow_html=True,
    )

with right_col:
    st.markdown("### Top 3 Suggestions")
    suggestions = current.get("suggestions", [])[:3]

    if not suggestions:
        st.info("No suggestions available for this product.")
    else:
        for suggestion in suggestions:
            badge = _confidence_badge(suggestion["confidence_label"])
            score = suggestion["confidence_score"]

            with st.container(border=True):
                st.markdown(f"**{badge}** · `{score:.3f}`")
                st.markdown(f"**{suggestion['name']}**")
                st.markdown(
                    f"<span style='color:#888;font-size:0.9rem;'>"
                    f"{suggestion['barcode']}</span>",
                    unsafe_allow_html=True,
                )
                if suggestion.get("explanation"):
                    st.markdown(f"*_{suggestion['explanation']}_*")

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
    if st.button("✅ APPROVE TOP MATCH", type="primary", use_container_width=True):
        if top_match and top_match.get("match_id"):
            _handle_decision(
                top_match["match_id"],
                "approved",
                "Top match approved",
            )
        else:
            st.error("No top match available.")

with btn_col2:
    if st.button("❌ REJECT ALL", use_container_width=True):
        pending_ids = [
            s["match_id"]
            for s in current.get("suggestions", [])
            if s.get("match_id")
        ]
        if not pending_ids:
            st.error("Nothing to reject.")
        else:
            results = [
                _submit_decision(match_id, "rejected", _operator_note(), count_session=False)
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
            elif not st.session_state.api_online:
                st.warning(OFFLINE_MESSAGE)

st.text_input("Operator note (optional)", key="operator_note", placeholder="Add context for this decision…")

initial = st.session_state.initial_pending or 0
reviewed = st.session_state.reviewed_count
total = max(initial, reviewed + pending_total)
progress = min(reviewed / total, 1.0) if total else 0.0

st.progress(progress, text=f"{reviewed} of {total} products reviewed")
