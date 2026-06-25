"""Match quality audit — size verdicts, guardrails, and conflict review.

Manual test: ``streamlit run ui/app.py`` → Quality tab (API must be running).
"""

from __future__ import annotations

import html
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from ui.api_client import api_get, api_post_json
from ui.utils.styles import (
    badge_html,
    inject_styles,
    match_quality_chip_html,
    match_source_chip_html,
    render_page_header,
    render_page_nav,
    render_section_header,
    section_label,
    show_offline_card,
    weight_pill_html,
    weight_tone,
)

REFRESH_SECONDS = 30
PAGE_SIZE = 20

TAB_VERDICTS: dict[str, str] = {
    "Size conflicts": "size_conflict",
    "Verified": "size_verified",
    "Incomplete": "size_unknown",
}

st.set_page_config(
    page_title="Quality · Trendbox",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles()

st.markdown(
    """
    <style>
    .quality-card {
      border: 1px solid #E5E7EB;
      border-radius: 12px;
      background: #FFFFFF;
      padding: 18px 20px;
      margin-bottom: 14px;
      transition: box-shadow 0.15s ease, transform 0.15s ease;
    }
    .quality-card:hover {
      box-shadow: 0 4px 16px rgba(17,24,39,0.06);
    }
    .quality-card.conflict {
      border-left: 4px solid #EF4444;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _esc(value: object) -> str:
    return html.escape(str(value or ""))


def _kpi_card(label: str, value: str, *, value_class: str = "lb-metric-value") -> None:
    with st.container(border=True):
        st.markdown(f'<div class="lb-metric-label">{label}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="{value_class}">{value}</div>',
            unsafe_allow_html=True,
        )


def _render_kpi_row(summary: dict) -> None:
    integrity = float(summary.get("catalog_integrity_pct", 0.0)) * 100.0
    conflicts = int(summary.get("size_conflict_count", 0))
    guardrails = int(summary.get("guardrail_blocked_count", 0))
    unknown = int(summary.get("size_unknown_count", 0))

    conflict_style = "color:#DC2626;" if conflicts > 0 else ""

    c1, c2, c3, c4 = st.columns(4, gap="medium")
    with c1:
        _kpi_card("CATALOG INTEGRITY", f"{integrity:.1f}%")
    with c2:
        with st.container(border=True):
            st.markdown('<div class="lb-metric-label">SIZE CONFLICTS</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="lb-metric-value" style="{conflict_style}">{conflicts:,}</div>',
                unsafe_allow_html=True,
            )
    with c3:
        _kpi_card("GUARDRAIL BLOCKS", f"{guardrails:,}")
    with c4:
        _kpi_card("SIZE UNKNOWN", f"{unknown:,}", value_class="lb-metric-value amber")


def _render_conflict_card(row: dict) -> None:
    query = row.get("query_product") or {}
    suggested = row.get("suggested_product") or {}
    query_weight = query.get("weight")
    suggested_weight = suggested.get("weight")
    confidence = float(row.get("confidence_score", 0.0))
    label = "HIGH" if confidence >= 0.9 else ("MEDIUM" if confidence >= 0.6 else "LOW")

    left_col, right_col = st.columns([2, 3], gap="large")
    with left_col:
        st.markdown(
            f"""
            <div class="quality-card conflict">
              <div class="section-label">SOURCE PRODUCT</div>
              <div style="font-size:18px; font-weight:700; color:#111827;
                          line-height:1.35; margin:10px 0 12px 0;">
                {_esc(query.get("name"))}
              </div>
              <div style="margin-bottom:10px;">
                {weight_pill_html(query_weight, tone=weight_tone(query_weight, suggested_weight))}
              </div>
              <div style="font-size:11px; color:#9CA3AF;">ID #{_esc(query.get("id"))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right_col:
        st.markdown(
            f"""
            <div class="quality-card conflict">
              <div style="display:flex; justify-content:space-between; align-items:flex-start;
                          gap:8px; flex-wrap:wrap; margin-bottom:8px;">
                <div class="section-label">SUGGESTED MATCH</div>
                <div style="display:flex; gap:6px; flex-wrap:wrap;">
                  {match_quality_chip_html(row.get("size_verdict"))}
                  {match_source_chip_html(row.get("match_source"))}
                </div>
              </div>
              <div style="font-size:18px; font-weight:700; color:#111827;
                          line-height:1.35; margin:8px 0 10px 0;">
                {_esc(suggested.get("name"))}
              </div>
              <div style="margin-bottom:10px;">
                {weight_pill_html(suggested_weight, tone=weight_tone(query_weight, suggested_weight))}
              </div>
              <div style="font-size:12px; color:#6B7280; margin-bottom:10px;">
                Barcode: <code>{_esc(suggested.get("barcode"))}</code>
                · Status: <strong>{_esc(row.get("status"))}</strong>
              </div>
              {badge_html(label, confidence)}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_conflict_actions(row: dict) -> None:
    """Operator actions for a size-conflict row."""
    match_id = row.get("match_id")
    status = (row.get("status") or "").lower()
    if not match_id:
        return

    show_reject = status in {"pending", "alternative"}
    show_reopen = status == "auto_rejected"
    if not show_reject and not show_reopen:
        return

    btn_cols = st.columns([1, 1, 4])
    if show_reject:
        with btn_cols[0]:
            if st.button("Reject match", key=f"quality_reject_{match_id}", use_container_width=True):
                data, offline = api_post_json(
                    f"/quality/matches/{match_id}/resolve",
                    json={"action": "reject"},
                )
                if offline:
                    show_offline_card()
                elif data is not None:
                    st.toast("Match rejected")
                    st.rerun()
                else:
                    st.error("Could not reject match.")
    if show_reopen:
        with btn_cols[1]:
            if st.button("Reopen", key=f"quality_reopen_{match_id}", use_container_width=True):
                data, offline = api_post_json(
                    f"/quality/matches/{match_id}/resolve",
                    json={"action": "reopen"},
                )
                if offline:
                    show_offline_card()
                elif data is not None:
                    st.toast("Match re-queued for review")
                    st.rerun()
                else:
                    st.error("Could not reopen match.")


def _render_compact_card(row: dict) -> None:
    query = row.get("query_product") or {}
    suggested = row.get("suggested_product") or {}
    query_weight = query.get("weight")
    suggested_weight = suggested.get("weight")
    tone = weight_tone(query_weight, suggested_weight)
    confidence = float(row.get("confidence_score", 0.0))
    label = "HIGH" if confidence >= 0.9 else ("MEDIUM" if confidence >= 0.6 else "LOW")

    st.markdown(
        f"""
        <div class="quality-card">
          <div style="display:flex; justify-content:space-between; align-items:flex-start;
                      gap:8px; flex-wrap:wrap; margin-bottom:10px;">
            <div>
              <div class="section-label">MATCH #{_esc(row.get("match_id"))}</div>
              <div style="font-size:11px; color:#9CA3AF; margin-top:4px;">
                Status: {_esc(row.get("status"))}
              </div>
            </div>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              {match_quality_chip_html(row.get("size_verdict"))}
              {match_source_chip_html(row.get("match_source"))}
            </div>
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">
            <div>
              <div style="font-size:11px; font-weight:600; color:#6B7280; margin-bottom:4px;">
                SOURCE
              </div>
              <div style="font-size:15px; font-weight:600; color:#111827; margin-bottom:8px;">
                {_esc(query.get("name"))}
              </div>
              {weight_pill_html(query_weight, tone=tone)}
            </div>
            <div>
              <div style="font-size:11px; font-weight:600; color:#6B7280; margin-bottom:4px;">
                SUGGESTION
              </div>
              <div style="font-size:15px; font-weight:600; color:#111827; margin-bottom:8px;">
                {_esc(suggested.get("name"))}
              </div>
              {weight_pill_html(suggested_weight, tone=tone)}
              <div style="font-size:11px; color:#9CA3AF; margin-top:8px;">
                {_esc(suggested.get("barcode"))}
              </div>
            </div>
          </div>
          <div style="margin-top:12px;">{badge_html(label, confidence)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pagination(total: int, page: int) -> None:
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    start = page * PAGE_SIZE + 1 if total else 0
    end = min((page + 1) * PAGE_SIZE, total)

    pag_l, pag_r = st.columns([3, 2])
    with pag_r:
        prev_col, info_col, next_col = st.columns([1, 3, 1])
        with prev_col:
            if st.button("‹", key="quality_pg_prev", disabled=page <= 0):
                st.session_state.quality_page -= 1
                st.rerun()
        with info_col:
            st.markdown(
                f'<div class="lb-pagination">'
                f"Rows per page: {PAGE_SIZE}&nbsp;&nbsp;"
                f"{start}–{end} of {total:,}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with next_col:
            if st.button("›", key="quality_pg_next", disabled=page >= total_pages - 1):
                st.session_state.quality_page += 1
                st.rerun()


def _render_quality_dashboard() -> None:
    render_page_nav("quality", alive=True)
    render_page_header(
        "Match quality",
        "Audit pack-size verdicts, guardrail blocks, and size conflicts across rank-1 matches.",
        eyebrow="Trendbox",
        live=True,
    )

    summary, offline = api_get("/quality/summary", timeout=10)
    if offline:
        show_offline_card()
    if summary is None:
        st.error("Could not load quality summary from the API.")
        return

    _render_kpi_row(summary)

    st.markdown("<br>", unsafe_allow_html=True)

    tab_labels = list(TAB_VERDICTS.keys())
    prev_tab = st.session_state.get("quality_tab_prev")
    st.radio(
        "Quality view",
        options=tab_labels,
        horizontal=True,
        label_visibility="collapsed",
        key="quality_tab",
    )
    active_tab = st.session_state.get("quality_tab", tab_labels[0])
    if prev_tab != active_tab:
        st.session_state.quality_page = 0
    st.session_state.quality_tab_prev = active_tab

    if "quality_page" not in st.session_state:
        st.session_state.quality_page = 0

    verdict = TAB_VERDICTS[active_tab]
    page = int(st.session_state.quality_page)
    offset = page * PAGE_SIZE

    matches_payload, matches_offline = api_get(
        "/quality/matches",
        timeout=15,
        params={"verdict": verdict, "limit": PAGE_SIZE, "offset": offset},
    )
    if matches_offline:
        show_offline_card()
    if matches_payload is None:
        st.error("Could not load quality matches from the API.")
        return

    items = matches_payload.get("items") or []
    total = int(matches_payload.get("total", 0))

    subtitles = {
        "Size conflicts": "Rank-1 pairs where both sides have a pack size and they differ.",
        "Verified": "Rank-1 pairs with matching extracted pack sizes.",
        "Incomplete": "Rank-1 pairs missing weight on one or both sides.",
    }
    render_section_header(active_tab, subtitles.get(active_tab, ""))

    if not items:
        st.markdown(
            f"""
            <div class="lb-card" style="text-align:center; padding:40px 20px;">
              <div style="font-size:15px; font-weight:600; color:#111827;">
                No matches in this band
              </div>
              <div style="font-size:13px; color:#6B7280; margin-top:8px;">
                Run batch processing to populate quality metadata.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif active_tab == "Size conflicts":
        for row in items:
            _render_conflict_card(row)
            _render_conflict_actions(row)
    else:
        for row in items:
            _render_compact_card(row)

    _render_pagination(total, page)

    st.markdown(
        f'<div style="text-align:right; font-size:11px; color:#9CA3AF; '
        f'margin-top:8px;">Last updated: {datetime.now().strftime("%H:%M:%S")}</div>',
        unsafe_allow_html=True,
    )


if "quality_page" not in st.session_state:
    st.session_state.quality_page = 0
if "quality_tab_prev" not in st.session_state:
    st.session_state.quality_tab_prev = st.session_state.get("quality_tab", "Size conflicts")


@st.fragment(run_every=REFRESH_SECONDS)
def _auto_refresh() -> None:
    _render_quality_dashboard()


_auto_refresh()
